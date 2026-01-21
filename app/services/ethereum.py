"""Ethereum connectivity service with RPC, retry logic, and nonce management."""
import asyncio
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from web3 import Web3
from web3.exceptions import TransactionNotFound
import httpx

from app.config import get_settings
from app.models.audit import AuditEventType
from app.services.audit import AuditService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class NonceManager:
    """Simple nonce manager to prevent nonce conflicts."""
    
    def __init__(self):
        self._nonces: Dict[str, int] = {}
        self._lock = asyncio.Lock()
    
    async def get_nonce(self, address: str, web3: Web3) -> int:
        """Get next nonce for address, handling pending transactions."""
        async with self._lock:
            address_lower = address.lower()
            
            # Get on-chain nonce (including pending)
            chain_nonce = web3.eth.get_transaction_count(address, "pending")
            
            # Use max of cached and chain nonce
            cached = self._nonces.get(address_lower, 0)
            nonce = max(chain_nonce, cached)
            
            # Increment for next use
            self._nonces[address_lower] = nonce + 1
            
            return nonce
    
    async def reset_nonce(self, address: str):
        """Reset cached nonce for address (e.g., after failed tx)."""
        async with self._lock:
            self._nonces.pop(address.lower(), None)


class EthereumService:
    """Service for Ethereum RPC interactions."""
    
    def __init__(self, db: AsyncSession, audit: AuditService):
        self.db = db
        self.audit = audit
        self.settings = get_settings()
        self._web3: Optional[Web3] = None
        self.nonce_manager = NonceManager()
    
    @property
    def web3(self) -> Web3:
        """Get Web3 instance (lazy loaded)."""
        if self._web3 is None:
            self._web3 = Web3(Web3.HTTPProvider(self.settings.eth_rpc_url))
        return self._web3
    
    @property
    def chain_id(self) -> int:
        """Get current chain ID."""
        return self.web3.eth.chain_id
    
    async def get_gas_price(self) -> Dict[str, int]:
        """Get current gas prices (legacy and EIP-1559)."""
        try:
            # Try EIP-1559 fee data first
            fee_history = self.web3.eth.fee_history(1, "latest", [25, 50, 75])
            base_fee = fee_history["baseFeePerGas"][-1]
            
            # Calculate priority fees from history
            priority_fees = fee_history["reward"][0] if fee_history["reward"] else [1_000_000_000]
            
            return {
                "base_fee": base_fee,
                "max_priority_fee": priority_fees[1] if len(priority_fees) > 1 else priority_fees[0],
                "max_fee": base_fee * 2 + priority_fees[1] if len(priority_fees) > 1 else base_fee * 2,
                "legacy_gas_price": self.web3.eth.gas_price
            }
        except Exception as e:
            logger.warning(f"Failed to get EIP-1559 fees: {e}, falling back to legacy")
            return {
                "legacy_gas_price": self.web3.eth.gas_price,
                "base_fee": None,
                "max_priority_fee": None,
                "max_fee": None
            }
    
    async def estimate_gas(
        self,
        from_address: str,
        to_address: str,
        value: int,
        data: Optional[str] = None
    ) -> int:
        """Estimate gas for transaction."""
        tx = {
            "from": Web3.to_checksum_address(from_address),
            "to": Web3.to_checksum_address(to_address),
            "value": value,
        }
        if data:
            tx["data"] = data
        
        try:
            estimate = self.web3.eth.estimate_gas(tx)
            # Add 20% buffer
            return int(estimate * 1.2)
        except Exception as e:
            logger.warning(f"Gas estimation failed: {e}, using default")
            return 21000 if not data else 100000
    
    async def get_nonce(self, address: str) -> int:
        """Get next nonce for address."""
        return await self.nonce_manager.get_nonce(address, self.web3)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, ConnectionError))
    )
    async def broadcast_transaction(
        self,
        signed_tx: str,
        tx_request_id: str,
        correlation_id: str
    ) -> str:
        """
        Broadcast signed transaction to the network.
        Returns tx_hash on success.
        """
        try:
            tx_hash = self.web3.eth.send_raw_transaction(bytes.fromhex(signed_tx.replace("0x", "")))
            tx_hash_hex = tx_hash.hex()
            
            # Log broadcast
            await self.audit.log_event(
                event_type=AuditEventType.TX_BROADCASTED,
                correlation_id=correlation_id,
                actor_type="SYSTEM",
                entity_type="TX_REQUEST",
                entity_id=tx_request_id,
                payload={
                    "tx_hash": tx_hash_hex,
                    "rpc_url": self.settings.eth_rpc_url.split("@")[-1]  # Hide any auth in URL
                }
            )
            
            return tx_hash_hex
            
        except Exception as e:
            logger.error(f"Broadcast failed for tx {tx_request_id}: {e}")
            raise
    
    async def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get transaction receipt if available."""
        try:
            receipt = self.web3.eth.get_transaction_receipt(tx_hash)
            return dict(receipt) if receipt else None
        except TransactionNotFound:
            return None
        except Exception as e:
            logger.warning(f"Failed to get receipt for {tx_hash}: {e}")
            return None
    
    async def get_block_number(self) -> int:
        """Get current block number."""
        return self.web3.eth.block_number
    
    async def get_block(self, block_number: int) -> Optional[Dict[str, Any]]:
        """Get block by number."""
        try:
            block = self.web3.eth.get_block(block_number, full_transactions=True)
            return dict(block) if block else None
        except Exception as e:
            logger.warning(f"Failed to get block {block_number}: {e}")
            return None
    
    async def check_confirmations(
        self,
        tx_hash: str,
        tx_request_id: str,
        correlation_id: str,
        required_confirmations: int = 3
    ) -> Optional[int]:
        """
        Check transaction confirmations.
        Returns number of confirmations or None if not found.
        """
        receipt = await self.get_transaction_receipt(tx_hash)
        if not receipt:
            return None
        
        if receipt.get("status") == 0:
            # Transaction failed on-chain
            logger.error(f"Transaction {tx_hash} failed on-chain")
            return -1
        
        tx_block = receipt.get("blockNumber")
        if not tx_block:
            return 0
        
        current_block = await self.get_block_number()
        confirmations = current_block - tx_block + 1
        
        if confirmations >= required_confirmations:
            await self.audit.log_event(
                event_type=AuditEventType.TX_CONFIRMED,
                correlation_id=correlation_id,
                actor_type="SYSTEM",
                entity_type="TX_REQUEST",
                entity_id=tx_request_id,
                payload={
                    "tx_hash": tx_hash,
                    "block_number": tx_block,
                    "confirmations": confirmations,
                    "required": required_confirmations,
                    "gas_used": receipt.get("gasUsed"),
                    "effective_gas_price": receipt.get("effectiveGasPrice")
                }
            )
        
        return confirmations
    
    async def get_balance(self, address: str) -> Decimal:
        """Get ETH balance for address."""
        balance_wei = self.web3.eth.get_balance(Web3.to_checksum_address(address))
        return Decimal(str(Web3.from_wei(balance_wei, "ether")))
    
    async def get_incoming_transfers(
        self,
        addresses: List[str],
        from_block: int,
        to_block: int
    ) -> List[Dict[str, Any]]:
        """
        Get incoming ETH transfers to monitored addresses.
        Note: For ERC20, would need to filter Transfer events.
        """
        transfers = []
        
        for block_num in range(from_block, to_block + 1):
            block = await self.get_block(block_num)
            if not block:
                continue
            
            for tx in block.get("transactions", []):
                to_addr = tx.get("to")
                if to_addr and to_addr.lower() in [a.lower() for a in addresses]:
                    value = tx.get("value", 0)
                    if value > 0:
                        transfers.append({
                            "tx_hash": tx.get("hash").hex() if isinstance(tx.get("hash"), bytes) else tx.get("hash"),
                            "from_address": tx.get("from"),
                            "to_address": to_addr,
                            "value": value,
                            "block_number": block_num,
                            "block_timestamp": block.get("timestamp")
                        })
        
        return transfers

