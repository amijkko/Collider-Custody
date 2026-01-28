"""Transaction request API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.tx_request import TxRequestCreate, TxRequestResponse, ApprovalCreate, ApprovalResponse
from app.schemas.common import CorrelatedResponse
from app.services.orchestrator import TxOrchestrator
from app.api.deps import (
    get_correlation_id,
    get_idempotency_key,
    get_current_user,
    get_orchestrator,
    require_roles
)
from app.models.user import User, UserRole
from app.models.tx_request import TxStatus

router = APIRouter(prefix="/v1/tx-requests", tags=["Transaction Requests"])


@router.post("", response_model=CorrelatedResponse[TxRequestResponse])
async def create_tx_request(
    tx_data: TxRequestCreate,
    db: AsyncSession = Depends(get_db),
    orchestrator: TxOrchestrator = Depends(get_orchestrator),
    current_user: User = Depends(get_current_user),  # Allow any authenticated user (demo mode)
    correlation_id: str = Depends(get_correlation_id),
    idempotency_key: Optional[str] = Depends(get_idempotency_key)
):
    """
    Create a new transaction request.
    
    This initiates the transaction workflow:
    SUBMITTED -> KYT -> POLICY -> APPROVALS -> SIGN -> BROADCAST -> CONFIRM
    
    Supports idempotency via Idempotency-Key header.
    """
    try:
        tx = await orchestrator.create_tx_request(
            tx_data,
            current_user.id,
            correlation_id,
            idempotency_key
        )
        await db.commit()
        
        return CorrelatedResponse(
            correlation_id=correlation_id,
            data=TxRequestResponse.model_validate(tx)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("")
async def list_tx_requests(
    wallet_id: Optional[str] = Query(None),
    status: Optional[TxStatus] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    orchestrator: TxOrchestrator = Depends(get_orchestrator),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id)
):
    """List transaction requests with optional filters."""
    txs = await orchestrator.list_tx_requests(
        wallet_id=wallet_id,
        status=status,
        limit=limit,
        offset=offset
    )

    # Convert to response objects and add permit expiration
    result_txs = []
    for tx in txs:
        # Validate and convert to dict
        tx_response = TxRequestResponse.model_validate(tx)
        tx_dict = tx_response.model_dump()

        # Add permit expiration if available
        if hasattr(tx, 'signing_permit') and tx.signing_permit:
            tx_dict['permit_expires_at'] = tx.signing_permit.expires_at.isoformat() if tx.signing_permit.expires_at else None

        result_txs.append(tx_dict)

    return {
        "correlation_id": correlation_id,
        "data": result_txs
    }


@router.get("/{tx_request_id}", response_model=CorrelatedResponse[TxRequestResponse])
async def get_tx_request(
    tx_request_id: str,
    orchestrator: TxOrchestrator = Depends(get_orchestrator),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id)
):
    """Get transaction request by ID."""
    tx = await orchestrator.get_tx_request(tx_request_id)
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction request {tx_request_id} not found"
        )
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=TxRequestResponse.model_validate(tx)
    )


@router.post("/{tx_request_id}/approve", response_model=CorrelatedResponse[ApprovalResponse])
async def approve_tx_request(
    tx_request_id: str,
    approval_data: ApprovalCreate,
    db: AsyncSession = Depends(get_db),
    orchestrator: TxOrchestrator = Depends(get_orchestrator),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR, UserRole.COMPLIANCE)),
    correlation_id: str = Depends(get_correlation_id)
):
    """
    Approve or reject a transaction request.
    
    SoD: The transaction creator cannot approve their own transaction.
    """
    try:
        tx, approval = await orchestrator.process_approval(
            tx_request_id,
            current_user.id,
            approval_data.decision,
            approval_data.comment,
            correlation_id
        )
        await db.commit()
        
        return CorrelatedResponse(
            correlation_id=correlation_id,
            data=ApprovalResponse.model_validate(approval)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{tx_request_id}/check-confirmation", response_model=CorrelatedResponse[TxRequestResponse])
async def check_tx_confirmation(
    tx_request_id: str,
    db: AsyncSession = Depends(get_db),
    orchestrator: TxOrchestrator = Depends(get_orchestrator),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id)
):
    """Manually trigger confirmation check for a transaction."""
    try:
        tx = await orchestrator.check_confirmation(tx_request_id, correlation_id)
        await db.commit()
        
        return CorrelatedResponse(
            correlation_id=correlation_id,
            data=TxRequestResponse.model_validate(tx)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{tx_request_id}/resume", response_model=CorrelatedResponse[TxRequestResponse])
async def resume_tx_after_kyt(
    tx_request_id: str,
    db: AsyncSession = Depends(get_db),
    orchestrator: TxOrchestrator = Depends(get_orchestrator),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.COMPLIANCE)),
    correlation_id: str = Depends(get_correlation_id)
):
    """Resume transaction processing after KYT case resolution."""
    try:
        tx = await orchestrator.resume_after_kyt_resolution(tx_request_id, correlation_id)
        await db.commit()
        
        return CorrelatedResponse(
            correlation_id=correlation_id,
            data=TxRequestResponse.model_validate(tx)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{tx_request_id}/sign", response_model=CorrelatedResponse[TxRequestResponse])
async def sign_tx_request(
    tx_request_id: str,
    db: AsyncSession = Depends(get_db),
    orchestrator: TxOrchestrator = Depends(get_orchestrator),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id)
):
    """
    Complete MPC signing for a transaction.
    
    Called by user after they have decrypted their local key share.
    The user's share participates in 2PC signing with the bank's share.
    """
    try:
        tx = await orchestrator.complete_mpc_signing(
            tx_request_id,
            str(current_user.id),
            correlation_id
        )
        await db.commit()
        
        return CorrelatedResponse(
            correlation_id=correlation_id,
            data=TxRequestResponse.model_validate(tx)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Signing failed: {str(e)}"
        )


from pydantic import BaseModel
from web3 import Web3


class SigningDataResponse(BaseModel):
    """Data needed for MPC signing."""
    tx_request_id: str
    wallet_id: str
    keyset_id: str | None
    message_hash: str
    to_address: str
    amount: str
    status: str


@router.get("/{tx_request_id}/signing-data", response_model=CorrelatedResponse[SigningDataResponse])
async def get_signing_data(
    tx_request_id: str,
    db: AsyncSession = Depends(get_db),
    orchestrator: TxOrchestrator = Depends(get_orchestrator),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id)
):
    """
    Get signing data for a transaction.

    Returns the message hash that needs to be signed via MPC.
    Only available for transactions in SIGN_PENDING status.
    """
    from app.models.tx_request import TxRequest
    from app.models.wallet import Wallet
    from sqlalchemy import select

    # Get transaction
    result = await db.execute(
        select(TxRequest).where(TxRequest.id == tx_request_id)
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction {tx_request_id} not found"
        )

    if tx.status != TxStatus.SIGN_PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transaction is not pending signature (status: {tx.status})"
        )

    # Get wallet
    wallet_result = await db.execute(
        select(Wallet).where(Wallet.id == tx.wallet_id)
    )
    wallet = wallet_result.scalar_one()

    # Compute message hash (hash of serialized transaction)
    # For EIP-155, we need to RLP encode: [nonce, gasPrice, gas, to, value, data, chainId, 0, 0]
    try:
        from eth_utils import to_bytes
        import rlp
        from decimal import Decimal
        from app.services.ethereum import EthereumService
        from app.services.audit import AuditService

        # Create ethereum service to get gas prices
        audit_service = AuditService(db)
        ethereum_service = EthereumService(db, audit_service)
        gas_prices = await ethereum_service.get_gas_price()

        # Convert Decimal/str to int safely
        if tx.asset == "ETH":
            try:
                value_wei = int(tx.amount)
            except (TypeError, ValueError):
                value_wei = int(Decimal(str(tx.amount)))
        else:
            value_wei = 0

        # Get nonce and gas parameters
        nonce = int(tx.nonce) if tx.nonce is not None else 0

        # Convert gas_price from Decimal to int
        if tx.gas_price is not None:
            try:
                gas_price = int(tx.gas_price)
            except (TypeError, ValueError):
                gas_price = int(Decimal(str(tx.gas_price)))
        else:
            gas_price = int(gas_prices.get("legacy_gas_price", 20000000000))  # 20 gwei default

        gas = int(tx.gas_limit) if tx.gas_limit is not None else 21000

        chain_id = 11155111  # Sepolia

        # Convert to bytes
        to = to_bytes(hexstr=tx.to_address)
        value = int(value_wei)
        data = to_bytes(hexstr=tx.data if tx.data else "0x")

        # EIP-155: unsigned tx = [nonce, gasPrice, gas, to, value, data, chainId, 0, 0]
        unsigned_tx = [nonce, gas_price, gas, to, value, data, chain_id, 0, 0]
        unsigned_tx_bytes = rlp.encode(unsigned_tx)
        message_hash = Web3.keccak(unsigned_tx_bytes).hex()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute message hash: {str(e)}"
        )

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=SigningDataResponse(
            tx_request_id=tx.id,
            wallet_id=str(tx.wallet_id),
            keyset_id=str(wallet.mpc_keyset_id) if wallet.mpc_keyset_id else None,
            message_hash=message_hash,
            to_address=tx.to_address,
            amount=str(tx.amount),
            status=tx.status.value if hasattr(tx.status, 'value') else str(tx.status),
        )
    )

