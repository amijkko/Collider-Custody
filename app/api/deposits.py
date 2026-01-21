"""Deposits API endpoints."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit import Deposit, AuditEventType
from app.models.wallet import Wallet
from app.models.user import User, UserRole
from app.api.deps import get_current_user, require_roles, get_correlation_id
from app.services.audit import AuditService

router = APIRouter(prefix="/v1/deposits", tags=["Deposits"])


class DepositResponse(BaseModel):
    """Deposit response model."""
    id: str
    wallet_id: str
    tx_hash: str
    from_address: str
    asset: str
    amount: str
    block_number: Optional[int] = None
    kyt_result: Optional[str] = None
    kyt_case_id: Optional[str] = None
    status: str  # PENDING_ADMIN, CREDITED, REJECTED
    detected_at: str
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

    class Config:
        from_attributes = True


class DepositListResponse(BaseModel):
    """Deposit list response."""
    data: list[DepositResponse]
    total: int
    correlation_id: str


class ApproveDepositRequest(BaseModel):
    """Request to approve a deposit."""
    pass


class RejectDepositRequest(BaseModel):
    """Request to reject a deposit."""
    reason: Optional[str] = None


def _deposit_to_response(deposit: Deposit) -> DepositResponse:
    """Convert deposit model to response."""
    # Use actual status from DB, fallback to computed status
    deposit_status = deposit.status
    if deposit.kyt_result == "BLOCK" and deposit_status == "PENDING_ADMIN":
        deposit_status = "KYT_BLOCKED"
    
    return DepositResponse(
        id=str(deposit.id),
        wallet_id=str(deposit.wallet_id),
        tx_hash=deposit.tx_hash,
        from_address=deposit.from_address,
        asset=deposit.asset,
        amount=deposit.amount,
        block_number=deposit.block_number,
        kyt_result=deposit.kyt_result,
        kyt_case_id=str(deposit.kyt_case_id) if deposit.kyt_case_id else None,
        status=deposit_status,
        detected_at=deposit.detected_at.isoformat() if deposit.detected_at else None,
        approved_by=deposit.approved_by,
        approved_at=deposit.approved_at.isoformat() if deposit.approved_at else None,
    )


@router.get("", response_model=DepositListResponse)
async def list_deposits(
    wallet_id: Optional[UUID] = Query(None, description="Filter by wallet ID"),
    status: Optional[str] = Query(None, description="Filter by status: PENDING_ADMIN, CREDITED, REJECTED"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """List deposits for the current user's wallets."""
    # Build query
    query = select(Deposit)
    
    # If not admin, filter to user's wallets only
    if current_user.role != UserRole.ADMIN:
        wallet_query = select(Wallet.id).where(
            Wallet.roles.any(user_id=current_user.id)
        )
        wallet_result = await db.execute(wallet_query)
        user_wallet_ids = [w[0] for w in wallet_result.fetchall()]
        
        if not user_wallet_ids:
            return DepositListResponse(data=[], total=0, correlation_id=correlation_id)
        
        query = query.where(Deposit.wallet_id.in_(user_wallet_ids))
    
    if wallet_id:
        query = query.where(Deposit.wallet_id == wallet_id)
    
    # Count total
    count_query = select(Deposit.id)
    if wallet_id:
        count_query = count_query.where(Deposit.wallet_id == wallet_id)
    count_result = await db.execute(count_query)
    total = len(count_result.fetchall())
    
    # Apply pagination
    query = query.order_by(Deposit.detected_at.desc()).offset(offset).limit(limit)
    
    result = await db.execute(query)
    deposits = result.scalars().all()
    
    return DepositListResponse(
        data=[_deposit_to_response(d) for d in deposits],
        total=total,
        correlation_id=correlation_id,
    )


@router.get("/admin", response_model=DepositListResponse)
async def list_all_deposits_admin(
    wallet_id: Optional[UUID] = Query(None, description="Filter by wallet ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    correlation_id: str = Depends(get_correlation_id),
):
    """List all deposits (admin only)."""
    query = select(Deposit)
    
    if wallet_id:
        query = query.where(Deposit.wallet_id == wallet_id)
    
    # Count total
    count_query = select(Deposit.id)
    if wallet_id:
        count_query = count_query.where(Deposit.wallet_id == wallet_id)
    count_result = await db.execute(count_query)
    total = len(count_result.fetchall())
    
    # Apply pagination
    query = query.order_by(Deposit.detected_at.desc()).offset(offset).limit(limit)
    
    result = await db.execute(query)
    deposits = result.scalars().all()
    
    return DepositListResponse(
        data=[_deposit_to_response(d) for d in deposits],
        total=total,
        correlation_id=correlation_id,
    )


@router.get("/{deposit_id}", response_model=DepositResponse)
async def get_deposit(
    deposit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """Get a specific deposit."""
    result = await db.execute(
        select(Deposit).where(Deposit.id == deposit_id)
    )
    deposit = result.scalar_one_or_none()
    
    if not deposit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deposit not found"
        )
    
    # Check access (admin or owner)
    if current_user.role != UserRole.ADMIN:
        wallet_result = await db.execute(
            select(Wallet).where(
                Wallet.id == deposit.wallet_id,
                Wallet.roles.any(user_id=current_user.id)
            )
        )
        if not wallet_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    
    return _deposit_to_response(deposit)


@router.post("/{deposit_id}/approve", response_model=DepositResponse)
async def approve_deposit(
    deposit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    correlation_id: str = Depends(get_correlation_id),
):
    """Approve a deposit (admin only) - credits the user balance."""
    from datetime import datetime
    
    result = await db.execute(
        select(Deposit).where(Deposit.id == deposit_id)
    )
    deposit = result.scalar_one_or_none()
    
    if not deposit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deposit not found"
        )
    
    # Check if already processed
    if deposit.status == "CREDITED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deposit already approved"
        )
    
    if deposit.status == "REJECTED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deposit was rejected"
        )
    
    # Check KYT result
    if deposit.kyt_result == "BLOCK":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve KYT-blocked deposit"
        )
    
    # Update deposit status
    deposit.status = "CREDITED"
    deposit.approved_by = str(current_user.id)
    deposit.approved_at = datetime.utcnow()
    
    # Log audit event
    audit = AuditService(db)
    await audit.log_event(
        event_type=AuditEventType.DEPOSIT_APPROVED,
        actor_id=str(current_user.id),
        entity_refs={"deposit_id": str(deposit_id), "wallet_id": str(deposit.wallet_id)},
        payload={"amount": deposit.amount, "asset": deposit.asset},
        correlation_id=correlation_id,
    )
    
    await db.commit()
    await db.refresh(deposit)
    
    return _deposit_to_response(deposit)


@router.post("/{deposit_id}/reject", response_model=DepositResponse)
async def reject_deposit(
    deposit_id: UUID,
    request: RejectDepositRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    correlation_id: str = Depends(get_correlation_id),
):
    """Reject a deposit (admin only)."""
    from datetime import datetime
    
    result = await db.execute(
        select(Deposit).where(Deposit.id == deposit_id)
    )
    deposit = result.scalar_one_or_none()
    
    if not deposit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deposit not found"
        )
    
    # Check if already processed
    if deposit.status in ("CREDITED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deposit already processed"
        )
    
    # Update deposit status
    deposit.status = "REJECTED"
    deposit.rejected_by = str(current_user.id)
    deposit.rejected_at = datetime.utcnow()
    deposit.rejection_reason = request.reason
    
    # Log audit event
    audit = AuditService(db)
    await audit.log_event(
        event_type=AuditEventType.DEPOSIT_REJECTED,
        actor_id=str(current_user.id),
        entity_refs={"deposit_id": str(deposit_id), "wallet_id": str(deposit.wallet_id)},
        payload={"amount": deposit.amount, "asset": deposit.asset, "reason": request.reason},
        correlation_id=correlation_id,
    )
    
    await db.commit()
    await db.refresh(deposit)
    
    return _deposit_to_response(deposit)

