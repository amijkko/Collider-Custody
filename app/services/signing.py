"""Signing adapter service with support for DEV_SIGNER and MPC_TECDSA."""
import logging
from typing import Optional, Tuple, TYPE_CHECKING

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

from app.config import get_settings
from app.models.tx_request import TxRequest
from app.models.wallet import CustodyBackend
from app.models.audit import AuditEventType
from app.services.audit import AuditService
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.services.mpc_coordinator import MPCCoordinator
    from app.models.mpc import SigningPermit

logger = logging.getLogger(__name__)


class SigningService:
    """
    Signing adapter for transaction signing.
    
    Supports two modes:
    1. DEV_SIGNER: Uses local private key from environment (development only)
    2. MPC_TECDSA: Uses MPC Coordinator for threshold ECDSA signing (production)
    """
    
    def __init__(
        self, 
        db: AsyncSession, 
        audit: AuditService,
        mpc_coordinator: Optional["MPCCoordinator"] = None
    ):
        self.db = db
        self.audit = audit
        self.settings = get_settings()
        self._dev_account: Optional[LocalAccount] = None
        self._mpc_coordinator = mpc_coordinator
    
    def set_mpc_coordinator(self, coordinator: "MPCCoordinator"):
        """Set the MPC coordinator (for dependency injection)."""
        self._mpc_coordinator = coordinator
    
    @property
    def dev_account(self) -> LocalAccount:
        """Get dev signer account (lazy loaded)."""
        if self._dev_account is None:
            self._dev_account = Account.from_key(self.settings.dev_signer_private_key)
        return self._dev_account
    
    async def sign_transaction(
        self,
        tx_request: TxRequest,
        chain_id: int,
        nonce: int,
        gas_price: int,
        gas_limit: int,
        max_fee_per_gas: Optional[int] = None,
        max_priority_fee_per_gas: Optional[int] = None,
        correlation_id: str = "",
        actor_id: Optional[str] = None,
        custody_backend: CustodyBackend = CustodyBackend.DEV_SIGNER,
        signing_permit: Optional["SigningPermit"] = None,
        keyset_id: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Sign an Ethereum transaction.
        
        Routes to appropriate signer based on custody_backend:
        - DEV_SIGNER: Uses local private key
        - MPC_TECDSA: Uses MPC Coordinator with SigningPermit
        
        Returns: (signed_tx_hex, tx_hash)
        """
        # Build transaction dict
        tx_dict = {
            "nonce": nonce,
            "to": Web3.to_checksum_address(tx_request.to_address),
            "value": int(tx_request.amount) if tx_request.asset == "ETH" else 0,  # amount is already in wei
            "gas": gas_limit,
            "chainId": chain_id,
        }
        
        # EIP-1559 or legacy
        if max_fee_per_gas and max_priority_fee_per_gas:
            tx_dict["maxFeePerGas"] = max_fee_per_gas
            tx_dict["maxPriorityFeePerGas"] = max_priority_fee_per_gas
            tx_dict["type"] = 2  # EIP-1559
        else:
            tx_dict["gasPrice"] = gas_price
        
        # Add data for contract calls
        if tx_request.data:
            tx_dict["data"] = tx_request.data
        
        # Route to appropriate signer
        if custody_backend == CustodyBackend.MPC_TECDSA:
            return await self._sign_with_mpc(
                tx_dict=tx_dict,
                tx_request=tx_request,
                signing_permit=signing_permit,
                keyset_id=keyset_id,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        else:
            return await self._sign_with_dev_signer(
                tx_dict=tx_dict,
                tx_request=tx_request,
                correlation_id=correlation_id,
                actor_id=actor_id,
                nonce=nonce,
                gas_limit=gas_limit,
                chain_id=chain_id,
            )
    
    async def _sign_with_dev_signer(
        self,
        tx_dict: dict,
        tx_request: TxRequest,
        correlation_id: str,
        actor_id: Optional[str],
        nonce: int,
        gas_limit: int,
        chain_id: int,
    ) -> Tuple[str, str]:
        """Sign transaction using dev signer (local private key)."""
        signed = self.dev_account.sign_transaction(tx_dict)
        
        # web3.py 6.x uses rawTransaction, earlier versions use raw_transaction
        raw_tx = getattr(signed, 'rawTransaction', None) or getattr(signed, 'raw_transaction', None)
        signed_tx_hex = raw_tx.hex()
        tx_hash = signed.hash.hex()
        
        # Log signing event (NO private key in audit!)
        await self.audit.log_event(
            event_type=AuditEventType.TX_SIGNED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_type="SYSTEM",
            entity_type="TX_REQUEST",
            entity_id=tx_request.id,
            payload={
                "tx_hash": tx_hash,
                "nonce": nonce,
                "gas_limit": gas_limit,
                "chain_id": chain_id,
                "signer_type": "DEV_LOCAL",
                "custody_backend": CustodyBackend.DEV_SIGNER.value,
            }
        )
        
        logger.info(f"Transaction signed with DEV_SIGNER: {tx_hash}")
        return signed_tx_hex, tx_hash
    
    async def _sign_with_mpc(
        self,
        tx_dict: dict,
        tx_request: TxRequest,
        signing_permit: Optional["SigningPermit"],
        keyset_id: Optional[str],
        correlation_id: str,
        actor_id: Optional[str],
    ) -> Tuple[str, str]:
        """Sign transaction using MPC Coordinator."""
        if not self._mpc_coordinator:
            raise ValueError("MPC Coordinator not configured")
        
        if not signing_permit:
            raise ValueError("SigningPermit required for MPC signing")
        
        if not keyset_id:
            raise ValueError("keyset_id required for MPC signing")
        
        # Sign using MPC
        raw_tx_bytes, tx_hash = await self._mpc_coordinator.sign_ethereum_transaction(
            keyset_id=keyset_id,
            tx_dict=tx_dict,
            permit=signing_permit,
            correlation_id=correlation_id,
            actor_id=actor_id,
        )
        
        signed_tx_hex = raw_tx_bytes.hex()
        
        # Log signing event
        await self.audit.log_event(
            event_type=AuditEventType.TX_SIGNED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_type="SYSTEM",
            entity_type="TX_REQUEST",
            entity_id=tx_request.id,
            payload={
                "tx_hash": tx_hash,
                "signer_type": "MPC_TECDSA",
                "custody_backend": CustodyBackend.MPC_TECDSA.value,
                "keyset_id": keyset_id,
                "permit_hash": signing_permit.permit_hash[:16] + "...",
            }
        )
        
        logger.info(f"Transaction signed with MPC_TECDSA: {tx_hash}")
        return signed_tx_hex, tx_hash
    
    async def get_signer_address(self, custody_backend: CustodyBackend = CustodyBackend.DEV_SIGNER) -> str:
        """Get the address of the signer (dev mode only, MPC uses keyset address)."""
        if custody_backend == CustodyBackend.DEV_SIGNER:
            return self.dev_account.address
        else:
            raise ValueError("MPC signer address is per-wallet (use keyset.address)")
    
    # Future HSM integration method (placeholder)
    
    async def _hsm_sign(self, tx_dict: dict, key_ref: str) -> Tuple[str, str]:
        """
        HSM signing integration placeholder.
        
        In production, this would:
        1. Connect to HSM (e.g., AWS CloudHSM, Azure Dedicated HSM)
        2. Use the key_ref to identify the signing key
        3. Send transaction hash for signing
        4. Return signed transaction
        """
        raise NotImplementedError("HSM integration not implemented")

