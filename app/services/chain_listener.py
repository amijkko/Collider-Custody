"""Chain Listener for confirmations and inbound deposit detection."""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.models.tx_request import TxRequest, TxStatus
from app.models.audit import Deposit, AuditEventType
from app.services.audit import AuditService
from app.services.wallet import WalletService
from app.services.kyt import KYTService
from app.services.ethereum import EthereumService
from app.services.orchestrator import TxOrchestrator

logger = logging.getLogger(__name__)


class ChainListener:
    """
    Background service that:
    1. Monitors pending transactions for confirmations
    2. Detects inbound deposits to monitored wallets
    """
    
    def __init__(
        self,
        session_maker: async_sessionmaker,
        poll_interval: int = 5
    ):
        self.session_maker = session_maker
        self.poll_interval = poll_interval
        self.settings = get_settings()
        self._running = False
        self._last_processed_block: Optional[int] = None
    
    async def start(self):
        """Start the chain listener."""
        self._running = True
        logger.info("Chain listener started")
        
        while self._running:
            try:
                await self._poll()
            except Exception as e:
                logger.error(f"Chain listener error: {e}", exc_info=True)
                # Continue running even if poll fails
                # This prevents the listener from stopping due to temporary RPC issues
            
            await asyncio.sleep(self.poll_interval)
    
    async def stop(self):
        """Stop the chain listener."""
        self._running = False
        logger.info("Chain listener stopped")
    
    async def _poll(self):
        """Single poll iteration."""
        async with self.session_maker() as session:
            # Initialize services
            audit = AuditService(session)
            wallet_service = WalletService(session, audit)
            kyt = KYTService(session, audit)
            ethereum = EthereumService(session, audit)
            
            # Check pending transaction confirmations
            await self._check_confirmations(session, audit, ethereum)
            
            # Check for inbound deposits
            await self._check_deposits(session, audit, wallet_service, kyt, ethereum)
            
            await session.commit()
    
    async def _check_confirmations(
        self,
        session: AsyncSession,
        audit: AuditService,
        ethereum: EthereumService
    ):
        """Check confirmations for pending transactions."""
        # Get all confirming transactions
        result = await session.execute(
            select(TxRequest).where(TxRequest.status == TxStatus.CONFIRMING)
        )
        pending_txs = list(result.scalars().all())
        
        for tx in pending_txs:
            if not tx.tx_hash:
                continue
            
            correlation_id = f"chain-listener-{uuid4()}"
            
            try:
                try:
                    confirmations = await ethereum.check_confirmations(
                        tx.tx_hash,
                        tx.id,
                        correlation_id,
                        self.settings.confirmation_blocks
                    )
                except Exception as rpc_error:
                    logger.warning(f"RPC connection failed while checking confirmations for tx {tx.id}: {rpc_error}")
                    continue
                
                if confirmations is None:
                    continue
                
                if confirmations == -1:
                    # Transaction failed
                    tx.status = TxStatus.FAILED_BROADCAST
                    await audit.log_event(
                        event_type=AuditEventType.TX_FAILED,
                        correlation_id=correlation_id,
                        actor_type="SYSTEM",
                        entity_type="TX_REQUEST",
                        entity_id=tx.id,
                        payload={
                            "tx_hash": tx.tx_hash,
                            "reason": "Transaction reverted on-chain"
                        }
                    )
                    continue
                
                tx.confirmations = confirmations
                
                # Get block number
                receipt = await ethereum.get_transaction_receipt(tx.tx_hash)
                if receipt:
                    tx.block_number = receipt.get("blockNumber")
                
                if confirmations >= self.settings.confirmation_blocks:
                    tx.status = TxStatus.CONFIRMED
                    
                    await audit.log_event(
                        event_type=AuditEventType.TX_CONFIRMED,
                        correlation_id=correlation_id,
                        actor_type="SYSTEM",
                        entity_type="TX_REQUEST",
                        entity_id=tx.id,
                        payload={
                            "tx_hash": tx.tx_hash,
                            "block_number": tx.block_number,
                            "confirmations": confirmations
                        }
                    )
                    
                    # Finalize
                    tx.status = TxStatus.FINALIZED
                    
                    await audit.log_event(
                        event_type=AuditEventType.TX_FINALIZED,
                        correlation_id=correlation_id,
                        actor_type="SYSTEM",
                        entity_type="TX_REQUEST",
                        entity_id=tx.id,
                        payload={
                            "tx_hash": tx.tx_hash,
                            "final_confirmations": confirmations
                        }
                    )
                    
            except Exception as e:
                logger.error(f"Error checking confirmation for tx {tx.id}: {e}")
    
    async def _check_deposits(
        self,
        session: AsyncSession,
        audit: AuditService,
        wallet_service: WalletService,
        kyt: KYTService,
        ethereum: EthereumService
    ):
        """Check for inbound deposits to monitored wallets."""
        try:
            # Check RPC connectivity first
            try:
                current_block = await ethereum.get_block_number()
            except Exception as rpc_error:
                logger.warning(f"RPC connection failed, skipping deposit check: {rpc_error}")
                return
            
            # Initialize last processed block
            if self._last_processed_block is None:
                # Start from a few blocks back
                self._last_processed_block = max(0, current_block - 10)
            
            # Don't scan too far ahead
            if current_block <= self._last_processed_block:
                return
            
            # Limit scan range
            from_block = self._last_processed_block + 1
            to_block = min(from_block + 10, current_block)
            
            # Get all monitored addresses
            addresses = await wallet_service.get_all_addresses()
            if not addresses:
                self._last_processed_block = to_block
                return
            
            # Get incoming transfers
            transfers = await ethereum.get_incoming_transfers(
                addresses,
                from_block,
                to_block
            )
            
            for transfer in transfers:
                await self._process_deposit(
                    session, audit, wallet_service, kyt,
                    transfer
                )
            
            self._last_processed_block = to_block
            
        except Exception as e:
            logger.error(f"Error checking deposits: {e}")
    
    async def _process_deposit(
        self,
        session: AsyncSession,
        audit: AuditService,
        wallet_service: WalletService,
        kyt: KYTService,
        transfer: dict
    ):
        """Process a detected inbound deposit."""
        tx_hash = transfer["tx_hash"]
        
        # Check if already processed
        existing = await session.execute(
            select(Deposit).where(Deposit.tx_hash == tx_hash)
        )
        if existing.scalar_one_or_none():
            return
        
        # Get wallet
        wallet = await wallet_service.get_wallet_by_address(transfer["to_address"])
        if not wallet:
            return
        
        correlation_id = f"deposit-{uuid4()}"
        
        # Create deposit record
        deposit = Deposit(
            id=str(uuid4()),
            wallet_id=wallet.id,
            tx_hash=tx_hash,
            from_address=transfer["from_address"].lower(),
            asset="ETH",
            amount=str(transfer["value"]),
            block_number=transfer["block_number"]
        )
        session.add(deposit)
        
        # Log deposit detection
        await audit.log_event(
            event_type=AuditEventType.DEPOSIT_DETECTED,
            correlation_id=correlation_id,
            actor_type="SYSTEM",
            entity_type="WALLET",
            entity_id=wallet.id,
            payload={
                "tx_hash": tx_hash,
                "from_address": transfer["from_address"],
                "amount_wei": str(transfer["value"]),
                "block_number": transfer["block_number"]
            }
        )
        
        # Run KYT on inbound
        kyt_result, kyt_case = await kyt.evaluate_inbound(
            transfer["from_address"],
            wallet.id,
            tx_hash,
            correlation_id
        )
        
        deposit.kyt_result = kyt_result
        if kyt_case:
            deposit.kyt_case_id = kyt_case.id
        
        logger.info(
            f"Deposit detected: {tx_hash} to wallet {wallet.id}, "
            f"amount: {transfer['value']} wei, KYT: {kyt_result}"
        )

