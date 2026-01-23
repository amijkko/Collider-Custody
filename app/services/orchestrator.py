"""Transaction Orchestrator - state machine for transaction workflow.

Flow v2 (tiered policies): Policy → KYT (conditional) → Approval (conditional) → Sign

The policy engine evaluates first and determines:
- Whether KYT check is required
- Whether approval is required
- Number of approvals needed
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple, TYPE_CHECKING
from uuid import uuid4
import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from app.models.tx_request import TxRequest, TxType, TxStatus, Approval, VALID_TRANSITIONS
from app.models.wallet import Wallet, WalletRoleType, CustodyBackend
from app.models.audit import AuditEventType, Deposit
from app.models.mpc import SigningPermit
from app.services.audit import AuditService
from app.services.kyt import KYTService, KYTResult
from app.services.policy import PolicyService
from app.services.policy_v2 import PolicyEngineV2, PolicyEvalResult
from app.services.group import GroupService
from app.services.address_book import AddressBookService
from app.services.signing import SigningService
from app.services.ethereum import EthereumService
from app.schemas.tx_request import TxRequestCreate

if TYPE_CHECKING:
    from app.services.mpc_coordinator import MPCCoordinator

logger = logging.getLogger(__name__)


class TxOrchestrator:
    """
    Orchestrates the complete transaction lifecycle (v2 flow):
    SUBMITTED -> POLICY -> KYT (conditional) -> APPROVALS (conditional) -> SIGN -> BROADCAST -> CONFIRM -> FINALIZE

    Policy evaluation happens first and determines:
    - Whether to BLOCK immediately (denylist)
    - Whether KYT check is required
    - Whether approval is required and how many

    Supports both DEV_SIGNER and MPC_TECDSA custody backends.
    """

    def __init__(
        self,
        db: AsyncSession,
        audit: AuditService,
        kyt: KYTService,
        policy: PolicyService,
        signing: SigningService,
        ethereum: EthereumService,
        mpc_coordinator: Optional["MPCCoordinator"] = None
    ):
        self.db = db
        self.audit = audit
        self.kyt = kyt
        self.policy = policy  # Legacy policy service (fallback)
        self.signing = signing
        self.ethereum = ethereum
        self.mpc_coordinator = mpc_coordinator

        # Initialize v2 policy engine components
        self.group_service = GroupService(db, audit)
        self.address_book = AddressBookService(db, audit)
        self.policy_v2 = PolicyEngineV2(db, audit, self.group_service, self.address_book)
    
    async def create_tx_request(
        self,
        tx_data: TxRequestCreate,
        created_by: str,
        correlation_id: str,
        idempotency_key: Optional[str] = None
    ) -> TxRequest:
        """Create a new transaction request and start processing."""
        # Check idempotency
        if idempotency_key:
            existing = await self.db.execute(
                select(TxRequest).where(TxRequest.idempotency_key == idempotency_key)
            )
            tx = existing.scalar_one_or_none()
            if tx:
                return tx
        
        # Verify wallet exists
        wallet_result = await self.db.execute(
            select(Wallet).where(Wallet.id == tx_data.wallet_id)
        )
        wallet = wallet_result.scalar_one_or_none()
        if not wallet:
            raise ValueError(f"Wallet {tx_data.wallet_id} not found")

        # Check ledger balance for MPC wallets (only CREDITED deposits are withdrawable)
        if wallet.custody_backend == CustodyBackend.MPC_TECDSA:
            credited_result = await self.db.execute(
                select(Deposit.amount)
                .where(Deposit.wallet_id == tx_data.wallet_id)
                .where(Deposit.status == "CREDITED")
            )
            credited_amounts = credited_result.scalars().all()
            available_wei = sum(int(amt) for amt in credited_amounts) if credited_amounts else 0
            available_eth = Decimal(available_wei) / Decimal(10**18)

            requested_wei = Decimal(tx_data.amount)
            requested_eth = requested_wei / Decimal(10**18)
            if requested_eth > available_eth:
                raise ValueError(
                    f"Insufficient balance. Available: {available_eth} ETH, Requested: {requested_eth} ETH"
                )

        # Create transaction request
        tx = TxRequest(
            id=str(uuid4()),
            wallet_id=tx_data.wallet_id,
            tx_type=tx_data.tx_type,
            to_address=tx_data.to_address.lower(),
            asset=tx_data.asset,
            amount=tx_data.amount,
            data=tx_data.data,
            status=TxStatus.SUBMITTED,
            created_by=created_by,
            idempotency_key=idempotency_key
        )
        
        self.db.add(tx)
        await self.db.flush()
        await self.db.refresh(tx, ["approvals"])  # Load relationship
        
        # Log creation
        await self.audit.log_event(
            event_type=AuditEventType.TX_REQUEST_CREATED,
            correlation_id=correlation_id,
            actor_id=created_by,
            entity_type="TX_REQUEST",
            entity_id=tx.id,
            entity_refs={"wallet_id": wallet.id},
            payload={
                "tx_type": tx.tx_type.value,
                "to_address": tx.to_address,
                "asset": tx.asset,
                "amount": str(tx.amount)
            }
        )

        # Start async processing (v2 flow: Policy first)
        await self._process_policy_v2(tx, wallet, created_by, correlation_id)

        return tx
    
    async def _transition_status(
        self,
        tx: TxRequest,
        new_status: TxStatus,
        correlation_id: str,
        actor_id: Optional[str] = None,
        extra_payload: Optional[dict] = None
    ) -> bool:
        """Transition transaction to new status if valid."""
        if not tx.can_transition_to(new_status):
            logger.warning(
                f"Invalid transition for tx {tx.id}: {tx.status} -> {new_status}"
            )
            return False
        
        old_status = tx.status
        tx.status = new_status
        tx.updated_at = datetime.utcnow()
        
        payload = {
            "old_status": old_status.value,
            "new_status": new_status.value
        }
        if extra_payload:
            payload.update(extra_payload)
        
        await self.audit.log_event(
            event_type=AuditEventType.TX_STATUS_CHANGED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_type="SYSTEM" if not actor_id else "USER",
            entity_type="TX_REQUEST",
            entity_id=tx.id,
            payload=payload
        )
        
        await self.db.flush()
        return True

    async def _process_policy_v2(
        self,
        tx: TxRequest,
        wallet: Wallet,
        actor_id: str,
        correlation_id: str,
    ):
        """
        Process policy evaluation using PolicyEngineV2 (tiered rules).

        This is the FIRST step in v2 flow. Policy determines:
        - BLOCK: Denylist or policy violation
        - ALLOW with kyt_required: Proceed to KYT check
        - ALLOW without kyt_required: Skip KYT
        - approval_required: Whether approvals are needed after KYT
        """
        await self._transition_status(tx, TxStatus.POLICY_EVAL_PENDING, correlation_id, actor_id)

        # Evaluate using v2 engine
        result: PolicyEvalResult = await self.policy_v2.evaluate(
            user_id=actor_id,
            to_address=tx.to_address,
            amount=tx.amount,
            asset=tx.asset,
            wallet=wallet,
            tx_request_id=tx.id,
            correlation_id=correlation_id,
        )

        # Store full policy result for explainability
        tx.policy_result = {
            "decision": result.decision,
            "allowed": result.allowed,
            "matched_rules": result.matched_rules,
            "reasons": result.reasons,
            "kyt_required": result.kyt_required,
            "approval_required": result.approval_required,
            "approval_count": result.approval_count,
            "policy_version": result.policy_version,
            "policy_snapshot_hash": result.policy_snapshot_hash,
            "group_id": result.group_id,
            "group_name": result.group_name,
            "address_status": result.address_status,
            "address_label": result.address_label,
            "evaluated_at": result.evaluated_at.isoformat(),
        }

        # Store control requirements on tx
        tx.requires_approval = result.approval_required
        tx.required_approvals = result.approval_count

        if not result.allowed:
            # Policy blocked (denylist, unknown address, no group)
            await self._transition_status(
                tx, TxStatus.POLICY_BLOCKED, correlation_id, actor_id,
                {
                    "blocked_by": result.matched_rules,
                    "reason": result.reasons[0] if result.reasons else "Policy blocked",
                    "address_status": result.address_status,
                }
            )
            return

        # Policy allowed - check if KYT is required
        if result.kyt_required:
            # Proceed to KYT evaluation
            await self._process_kyt_v2(tx, wallet, result, correlation_id, actor_id)
        else:
            # Skip KYT - log and proceed to approval check
            await self._transition_status(tx, TxStatus.KYT_SKIPPED, correlation_id, actor_id)

            await self.audit.log_event(
                event_type=AuditEventType.KYT_SKIPPED,
                correlation_id=correlation_id,
                actor_id=actor_id,
                actor_type="SYSTEM",
                entity_type="TX_REQUEST",
                entity_id=tx.id,
                payload={
                    "reason": "Policy rule does not require KYT",
                    "matched_rules": result.matched_rules,
                    "policy_version": result.policy_version,
                }
            )

            # Check if approval is required
            await self._process_approval_gate(tx, wallet, result, correlation_id, actor_id)

    async def _process_kyt_v2(
        self,
        tx: TxRequest,
        wallet: Wallet,
        policy_result: PolicyEvalResult,
        correlation_id: str,
        actor_id: Optional[str] = None
    ):
        """Process KYT evaluation (v2 flow - after policy)."""
        await self._transition_status(tx, TxStatus.KYT_PENDING, correlation_id, actor_id)

        # Evaluate KYT
        result, case = await self.kyt.evaluate_outbound(
            tx.to_address,
            tx.id,
            correlation_id,
            actor_id
        )

        tx.kyt_result = result
        if case:
            tx.kyt_case_id = case.id

        if result == KYTResult.BLOCK:
            await self._transition_status(tx, TxStatus.KYT_BLOCKED, correlation_id, actor_id)
            return

        if result == KYTResult.REVIEW:
            await self._transition_status(tx, TxStatus.KYT_REVIEW, correlation_id, actor_id)
            return  # Wait for manual resolution

        # KYT passed, check approval requirement
        await self._process_approval_gate(tx, wallet, policy_result, correlation_id, actor_id)

    async def _process_approval_gate(
        self,
        tx: TxRequest,
        wallet: Wallet,
        policy_result: PolicyEvalResult,
        correlation_id: str,
        actor_id: Optional[str] = None
    ):
        """
        Check if approval is required based on policy result.

        If approval required: transition to APPROVAL_PENDING
        If not required: skip to signing
        """
        if policy_result.approval_required and policy_result.approval_count > 0:
            # Approval required
            await self._transition_status(tx, TxStatus.APPROVAL_PENDING, correlation_id, actor_id)
            return  # Wait for approvals

        # No approval required - fast track to signing
        await self._transition_status(tx, TxStatus.APPROVAL_SKIPPED, correlation_id, actor_id)

        await self.audit.log_event(
            event_type=AuditEventType.APPROVALS_SKIPPED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_type="SYSTEM",
            entity_type="TX_REQUEST",
            entity_id=tx.id,
            payload={
                "reason": "Policy rule does not require approval",
                "matched_rules": policy_result.matched_rules,
                "policy_version": policy_result.policy_version,
            }
        )

        # Proceed to signing
        await self._process_signing(tx, wallet, correlation_id, actor_id)

    async def _process_kyt(
        self,
        tx: TxRequest,
        wallet: Wallet,
        correlation_id: str,
        actor_id: Optional[str] = None
    ):
        """Process KYT evaluation."""
        await self._transition_status(tx, TxStatus.KYT_PENDING, correlation_id, actor_id)
        
        # Evaluate KYT
        result, case = await self.kyt.evaluate_outbound(
            tx.to_address,
            tx.id,
            correlation_id,
            actor_id
        )
        
        tx.kyt_result = result
        if case:
            tx.kyt_case_id = case.id
        
        if result == KYTResult.BLOCK:
            await self._transition_status(tx, TxStatus.KYT_BLOCKED, correlation_id, actor_id)
            return
        
        if result == KYTResult.REVIEW:
            await self._transition_status(tx, TxStatus.KYT_REVIEW, correlation_id, actor_id)
            return  # Wait for manual resolution
        
        # KYT passed, proceed to policy
        await self._process_policy(tx, wallet, correlation_id, actor_id)
    
    async def _process_policy(
        self,
        tx: TxRequest,
        wallet: Wallet,
        correlation_id: str,
        actor_id: Optional[str] = None
    ):
        """Process policy evaluation."""
        await self._transition_status(tx, TxStatus.POLICY_EVAL_PENDING, correlation_id, actor_id)
        
        # Evaluate policies
        result = await self.policy.evaluate(tx, wallet, correlation_id, actor_id)
        
        tx.policy_result = {
            "allowed": result.allowed,
            "requires_approval": result.requires_approval,
            "required_approvals": result.required_approvals,
            "blocked_by": result.blocked_by,
            "reason": result.reason,
            "evaluated_policies": result.evaluated_policies
        }
        
        if not result.allowed:
            await self._transition_status(
                tx, TxStatus.POLICY_BLOCKED, correlation_id, actor_id,
                {"blocked_by": result.blocked_by, "reason": result.reason}
            )
            return
        
        tx.requires_approval = result.requires_approval
        tx.required_approvals = result.required_approvals
        
        if result.requires_approval:
            await self._transition_status(tx, TxStatus.APPROVAL_PENDING, correlation_id, actor_id)
            return  # Wait for approvals
        
        # No approvals needed, proceed to signing
        await self._process_signing(tx, wallet, correlation_id, actor_id)
    
    async def process_approval(
        self,
        tx_request_id: str,
        user_id: str,
        decision: str,
        comment: Optional[str],
        correlation_id: str
    ) -> Tuple[TxRequest, Approval]:
        """Process an approval or rejection for a transaction."""
        # Get transaction
        tx_result = await self.db.execute(
            select(TxRequest).where(TxRequest.id == tx_request_id)
        )
        tx = tx_result.scalar_one_or_none()
        if not tx:
            raise ValueError(f"Transaction {tx_request_id} not found")
        
        if tx.status != TxStatus.APPROVAL_PENDING:
            raise ValueError(f"Transaction {tx_request_id} is not pending approval")
        
        # SoD: Creator cannot approve their own transaction
        if tx.created_by == user_id:
            raise ValueError("Segregation of Duties: Transaction creator cannot be approver")
        
        # Check if user already voted
        existing_result = await self.db.execute(
            select(Approval)
            .where(Approval.tx_request_id == tx_request_id)
            .where(Approval.user_id == user_id)
        )
        if existing_result.scalar_one_or_none():
            raise ValueError("User has already voted on this transaction")
        
        # Create approval record
        approval = Approval(
            id=str(uuid4()),
            tx_request_id=tx_request_id,
            user_id=user_id,
            decision=decision,
            comment=comment
        )
        self.db.add(approval)
        await self.db.flush()
        
        # Log approval
        event_type = (
            AuditEventType.TX_APPROVAL_RECEIVED 
            if decision == "APPROVED" 
            else AuditEventType.TX_REJECTION_RECEIVED
        )
        await self.audit.log_event(
            event_type=event_type,
            correlation_id=correlation_id,
            actor_id=user_id,
            entity_type="TX_REQUEST",
            entity_id=tx_request_id,
            payload={
                "decision": decision,
                "comment": comment
            }
        )
        
        # Check if we have enough approvals/rejections
        approvals_result = await self.db.execute(
            select(Approval).where(Approval.tx_request_id == tx_request_id)
        )
        all_approvals = list(approvals_result.scalars().all())
        
        approved_count = sum(1 for a in all_approvals if a.decision == "APPROVED")
        rejected_count = sum(1 for a in all_approvals if a.decision == "REJECTED")
        
        if decision == "REJECTED":
            # Any rejection blocks the transaction
            await self._transition_status(tx, TxStatus.REJECTED, correlation_id, user_id)
        elif approved_count >= tx.required_approvals:
            # Enough approvals, proceed to signing
            wallet_result = await self.db.execute(
                select(Wallet).where(Wallet.id == tx.wallet_id)
            )
            wallet = wallet_result.scalar_one()
            await self._process_signing(tx, wallet, correlation_id, user_id)
        
        return tx, approval
    
    async def _process_signing(
        self,
        tx: TxRequest,
        wallet: Wallet,
        correlation_id: str,
        actor_id: Optional[str] = None
    ):
        """Sign the transaction using appropriate custody backend."""
        await self._transition_status(tx, TxStatus.SIGN_PENDING, correlation_id, actor_id)
        
        try:
            # Determine signer address based on custody backend
            if wallet.custody_backend == CustodyBackend.MPC_TECDSA:
                signer_address = Web3.to_checksum_address(wallet.address)
            else:
                signer_address = await self.signing.get_signer_address()
            
            # Get gas prices
            gas_prices = await self.ethereum.get_gas_price()
            
            # Estimate gas
            value = Web3.to_wei(tx.amount, "ether") if tx.asset == "ETH" else 0
            gas_limit = await self.ethereum.estimate_gas(
                signer_address,
                tx.to_address,
                value,
                tx.data
            )
            
            # Get nonce
            nonce = await self.ethereum.get_nonce(signer_address)
            
            # Store tx params for later signing
            tx.gas_limit = gas_limit
            tx.gas_price = gas_prices.get("legacy_gas_price")
            tx.nonce = nonce
            
            if wallet.custody_backend == CustodyBackend.MPC_TECDSA:
                # For MPC wallets: Issue SigningPermit and STOP here.
                # User must complete signing through frontend UI.
                signing_permit = await self._issue_signing_permit(
                    tx, wallet, correlation_id, actor_id
                )
                logger.info(f"MPC signing permit issued for tx {tx.id}, awaiting user signature")
                # Don't proceed - user needs to sign through UI
                return
            
            # For DEV_SIGNER: auto-sign immediately
            signed_tx, tx_hash = await self.signing.sign_transaction(
                tx,
                self.ethereum.chain_id,
                nonce,
                gas_prices.get("legacy_gas_price", 0),
                gas_limit,
                max_fee_per_gas=gas_prices.get("max_fee"),
                max_priority_fee_per_gas=gas_prices.get("max_priority_fee"),
                correlation_id=correlation_id,
                actor_id=actor_id,
                custody_backend=wallet.custody_backend,
            )
            
            tx.signed_tx = signed_tx
            tx.tx_hash = tx_hash
            
            await self._transition_status(tx, TxStatus.SIGNED, correlation_id, actor_id)
            
            # Proceed to broadcast
            await self._process_broadcast(tx, correlation_id, actor_id)
            
        except Exception as e:
            logger.error(f"Signing failed for tx {tx.id}: {e}")
            await self._transition_status(
                tx, TxStatus.FAILED_SIGN, correlation_id, actor_id,
                {"error": str(e)}
            )
    
    async def _issue_signing_permit(
        self,
        tx: TxRequest,
        wallet: Wallet,
        correlation_id: str,
        actor_id: Optional[str] = None
    ):
        """
        Issue a SigningPermit for MPC signing.
        
        The permit proves that all controls (KYT, Policy, Approvals) have passed.
        """
        if not self.mpc_coordinator:
            raise ValueError("MPC Coordinator not configured")
        
        if not wallet.mpc_keyset_id:
            raise ValueError(f"Wallet {wallet.id} has no MPC keyset")
        
        # Get current audit anchor
        last_audit = await self.audit.get_last_audit_event()
        audit_anchor_hash = last_audit.hash if last_audit else "genesis"
        
        # Collect approval snapshot
        approvals_result = await self.db.execute(
            select(Approval).where(Approval.tx_request_id == tx.id)
        )
        approvals = list(approvals_result.scalars().all())
        approval_snapshot = {
            "count": len([a for a in approvals if a.decision == "APPROVED"]),
            "required": tx.required_approvals,
            "approvers": [a.user_id for a in approvals if a.decision == "APPROVED"],
        }
        
        # Create permit via MPC Coordinator
        # Note: tx_hash is computed from canonical tx payload
        tx_hash_for_permit = Web3.keccak(text=f"{tx.id}:{tx.to_address}:{tx.amount}").hex()
        
        permit = self.mpc_coordinator.issue_signing_permit(
            tx_request_id=tx.id,
            wallet_id=wallet.id,
            keyset_id=wallet.mpc_keyset_id,
            tx_hash=tx_hash_for_permit,
            kyt_result=tx.kyt_result or "ALLOW",
            kyt_snapshot={"case_id": tx.kyt_case_id} if tx.kyt_case_id else {},
            policy_result="ALLOWED",
            policy_snapshot=tx.policy_result or {},
            approval_snapshot=approval_snapshot,
            audit_anchor_hash=audit_anchor_hash,
        )
        
        # Save permit to DB
        self.db.add(permit)
        await self.db.flush()
        
        # Log permit issuance
        await self.audit.log_event(
            event_type=AuditEventType.SIGN_PERMIT_ISSUED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_type="SYSTEM",
            entity_type="SIGNING_PERMIT",
            entity_id=permit.id,
            payload={
                "tx_request_id": tx.id,
                "wallet_id": wallet.id,
                "keyset_id": wallet.mpc_keyset_id,
                "permit_hash": permit.permit_hash[:16] + "...",
                "expires_at": permit.expires_at.isoformat(),
            }
        )
        
        logger.info(f"SigningPermit issued for tx {tx.id}: {permit.id}")
        return permit
    
    async def complete_mpc_signing(
        self,
        tx_request_id: str,
        user_id: str,
        correlation_id: str
    ) -> TxRequest:
        """
        Complete MPC signing initiated by user.
        
        Called when user has decrypted their key share and is ready to participate
        in the 2PC signing protocol.
        """
        # Get transaction
        tx_result = await self.db.execute(
            select(TxRequest).where(TxRequest.id == tx_request_id)
        )
        tx = tx_result.scalar_one_or_none()
        if not tx:
            raise ValueError(f"Transaction {tx_request_id} not found")
        
        if tx.status != TxStatus.SIGN_PENDING:
            raise ValueError(f"Transaction is not pending signature (status: {tx.status})")
        
        # Get wallet
        wallet_result = await self.db.execute(
            select(Wallet).where(Wallet.id == tx.wallet_id)
        )
        wallet = wallet_result.scalar_one()
        
        if wallet.custody_backend != CustodyBackend.MPC_TECDSA:
            raise ValueError("This endpoint is only for MPC wallets")
        
        # Check user has permission on this wallet
        # (TODO: add proper wallet role check)
        
        # Get the valid signing permit
        permit_result = await self.db.execute(
            select(SigningPermit).where(
                SigningPermit.tx_request_id == tx_request_id,
                SigningPermit.is_used == False,
                SigningPermit.is_revoked == False,
            )
        )
        permit = permit_result.scalar_one_or_none()
        if not permit:
            raise ValueError("No valid signing permit found. Please re-approve the transaction.")
        
        # Check permit not expired
        from datetime import datetime
        if permit.expires_at < datetime.utcnow():
            raise ValueError("Signing permit has expired. Please re-approve the transaction.")
        
        try:
            # Perform MPC signing
            signer_address = Web3.to_checksum_address(wallet.address)
            gas_prices = await self.ethereum.get_gas_price()
            
            signed_tx, tx_hash = await self.signing.sign_transaction(
                tx,
                self.ethereum.chain_id,
                tx.nonce,
                tx.gas_price or gas_prices.get("legacy_gas_price", 0),
                tx.gas_limit,
                max_fee_per_gas=gas_prices.get("max_fee"),
                max_priority_fee_per_gas=gas_prices.get("max_priority_fee"),
                correlation_id=correlation_id,
                actor_id=user_id,
                custody_backend=wallet.custody_backend,
                signing_permit=permit,
                keyset_id=wallet.mpc_keyset_id,
            )
            
            # Mark permit as used
            permit.is_used = True
            permit.used_at = datetime.utcnow()
            
            tx.signed_tx = signed_tx
            tx.tx_hash = tx_hash
            
            await self._transition_status(tx, TxStatus.SIGNED, correlation_id, user_id)
            
            # Proceed to broadcast
            await self._process_broadcast(tx, correlation_id, user_id)
            
            return tx
            
        except Exception as e:
            logger.error(f"MPC signing failed for tx {tx.id}: {e}")
            await self._transition_status(
                tx, TxStatus.FAILED_SIGN, correlation_id, user_id,
                {"error": str(e)}
            )
            raise
    
    async def _process_broadcast(
        self,
        tx: TxRequest,
        correlation_id: str,
        actor_id: Optional[str] = None
    ):
        """Broadcast the signed transaction."""
        await self._transition_status(tx, TxStatus.BROADCAST_PENDING, correlation_id, actor_id)
        
        try:
            tx_hash = await self.ethereum.broadcast_transaction(
                tx.signed_tx,
                tx.id,
                correlation_id
            )
            
            tx.tx_hash = tx_hash
            await self._transition_status(tx, TxStatus.BROADCASTED, correlation_id, actor_id)
            
            # Move to confirming state
            await self._transition_status(tx, TxStatus.CONFIRMING, correlation_id, actor_id)
            
        except Exception as e:
            logger.error(f"Broadcast failed for tx {tx.id}: {e}")
            await self._transition_status(
                tx, TxStatus.FAILED_BROADCAST, correlation_id, actor_id,
                {"error": str(e)}
            )
    
    async def check_confirmation(
        self,
        tx_request_id: str,
        correlation_id: str
    ) -> TxRequest:
        """Check and update transaction confirmation status."""
        tx_result = await self.db.execute(
            select(TxRequest).where(TxRequest.id == tx_request_id)
        )
        tx = tx_result.scalar_one_or_none()
        if not tx:
            raise ValueError(f"Transaction {tx_request_id} not found")
        
        if tx.status != TxStatus.CONFIRMING:
            return tx
        
        if not tx.tx_hash:
            return tx
        
        confirmations = await self.ethereum.check_confirmations(
            tx.tx_hash,
            tx.id,
            correlation_id,
            self.ethereum.settings.confirmation_blocks
        )
        
        if confirmations is None:
            return tx  # Still waiting
        
        if confirmations == -1:
            # Transaction failed on-chain
            await self._transition_status(
                tx, TxStatus.FAILED_BROADCAST, correlation_id, None,
                {"reason": "Transaction reverted on-chain"}
            )
            return tx
        
        tx.confirmations = confirmations
        
        # Get block number from receipt
        receipt = await self.ethereum.get_transaction_receipt(tx.tx_hash)
        if receipt:
            tx.block_number = receipt.get("blockNumber")
        
        if confirmations >= self.ethereum.settings.confirmation_blocks:
            await self._transition_status(tx, TxStatus.CONFIRMED, correlation_id)
            
            # Update daily volume
            wallet_result = await self.db.execute(
                select(Wallet).where(Wallet.id == tx.wallet_id)
            )
            wallet = wallet_result.scalar_one()
            await self.policy.update_daily_volume(wallet.id, tx.asset, tx.amount)
            
            # Finalize
            await self._transition_status(tx, TxStatus.FINALIZED, correlation_id)
            
            await self.audit.log_event(
                event_type=AuditEventType.TX_FINALIZED,
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
        
        await self.db.flush()
        return tx
    
    async def resume_after_kyt_resolution(
        self,
        tx_request_id: str,
        correlation_id: str
    ) -> TxRequest:
        """
        Resume processing after KYT case resolution (v2 flow).

        In v2, policy was already evaluated. After KYT resolution:
        - If BLOCK: transition to KYT_BLOCKED
        - If ALLOW: check approval requirement from stored policy result
        """
        tx_result = await self.db.execute(
            select(TxRequest).where(TxRequest.id == tx_request_id)
        )
        tx = tx_result.scalar_one_or_none()
        if not tx:
            raise ValueError(f"Transaction {tx_request_id} not found")

        if tx.status != TxStatus.KYT_REVIEW:
            raise ValueError(f"Transaction is not in KYT_REVIEW status")

        # Check case resolution
        case = await self.kyt.get_case(tx.kyt_case_id)
        if not case or case.status == "PENDING":
            raise ValueError("KYT case is not resolved")

        if case.status == "RESOLVED_BLOCK":
            await self._transition_status(tx, TxStatus.KYT_BLOCKED, correlation_id)
            return tx

        # Case resolved with ALLOW - check approval requirement from stored policy
        wallet_result = await self.db.execute(
            select(Wallet).where(Wallet.id == tx.wallet_id)
        )
        wallet = wallet_result.scalar_one()

        # Reconstruct policy result from stored data
        policy_data = tx.policy_result or {}
        policy_result = PolicyEvalResult(
            decision=policy_data.get("decision", "ALLOW"),
            allowed=policy_data.get("allowed", True),
            matched_rules=policy_data.get("matched_rules", []),
            reasons=policy_data.get("reasons", []),
            kyt_required=policy_data.get("kyt_required", True),
            approval_required=policy_data.get("approval_required", False),
            approval_count=policy_data.get("approval_count", 0),
            policy_version=policy_data.get("policy_version", ""),
            policy_snapshot_hash=policy_data.get("policy_snapshot_hash", ""),
            group_id=policy_data.get("group_id"),
            group_name=policy_data.get("group_name"),
            address_status=policy_data.get("address_status", "unknown"),
            address_label=policy_data.get("address_label"),
        )

        # Proceed to approval gate
        await self._process_approval_gate(tx, wallet, policy_result, correlation_id)

        return tx
    
    async def get_tx_request(self, tx_request_id: str) -> Optional[TxRequest]:
        """Get transaction request by ID."""
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(TxRequest).options(selectinload(TxRequest.approvals)).where(TxRequest.id == tx_request_id)
        )
        return result.scalar_one_or_none()
    
    async def list_tx_requests(
        self,
        wallet_id: Optional[str] = None,
        status: Optional[TxStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list:
        """List transaction requests with optional filters."""
        from sqlalchemy.orm import selectinload
        query = select(TxRequest).options(selectinload(TxRequest.approvals))
        
        if wallet_id:
            query = query.where(TxRequest.wallet_id == wallet_id)
        if status:
            query = query.where(TxRequest.status == status)
        
        query = query.order_by(TxRequest.created_at.desc()).limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

