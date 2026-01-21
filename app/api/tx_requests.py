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
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR)),
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


@router.get("", response_model=CorrelatedResponse[List[TxRequestResponse]])
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
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=[TxRequestResponse.model_validate(tx) for tx in txs]
    )


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

