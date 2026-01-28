"""Audit API endpoints."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.schemas.audit import AuditPackageResponse, AuditVerifyResponse
from app.schemas.common import CorrelatedResponse
from app.services.audit import AuditService
from app.api.deps import (
    get_correlation_id,
    get_current_user,
    get_audit_service,
    require_roles
)
from app.models.user import User, UserRole
from app.models.audit import AuditEvent, AuditEventType

router = APIRouter(prefix="/v1/audit", tags=["Audit"])


class LoginEventResponse(BaseModel):
    """Response model for login event."""
    timestamp: datetime
    username: str
    user_id: str
    event_id: str
    correlation_id: str


@router.get("/packages/{tx_request_id}", response_model=CorrelatedResponse[AuditPackageResponse])
async def get_audit_package(
    tx_request_id: str,
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.COMPLIANCE)),
    correlation_id: str = Depends(get_correlation_id)
):
    """
    Get complete audit package for a transaction request.
    
    Returns aggregated audit trail including:
    - Transaction request details
    - Policy evaluation results
    - KYT evaluation results
    - All approvals
    - Signing information
    - Broadcast details
    - Confirmation status
    - All related audit events
    - Package hash for verification
    """
    try:
        package = await audit_service.build_audit_package(
            tx_request_id,
            correlation_id
        )
        
        return CorrelatedResponse(
            correlation_id=correlation_id,
            data=package
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/verify", response_model=CorrelatedResponse[AuditVerifyResponse])
async def verify_audit_chain(
    from_sequence: Optional[int] = Query(None, description="Start verification from this sequence number"),
    to_sequence: Optional[int] = Query(None, description="End verification at this sequence number"),
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    correlation_id: str = Depends(get_correlation_id)
):
    """
    Verify integrity of the audit log hash chain.

    Returns verification result including:
    - Whether chain is valid (no tampering detected)
    - Number of events verified
    - Any errors found
    """
    result = await audit_service.verify_chain(
        from_sequence=from_sequence,
        to_sequence=to_sequence
    )

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=result
    )


@router.get("/logins", response_model=CorrelatedResponse[List[LoginEventResponse]])
async def get_recent_logins(
    limit: int = Query(20, le=100, description="Maximum number of login events to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    correlation_id: str = Depends(get_correlation_id)
):
    """
    Get recent user login events.

    Returns list of login events with user information.
    Requires ADMIN role.
    """
    # Query for USER_LOGIN events
    stmt = (
        select(AuditEvent, User)
        .outerjoin(User, AuditEvent.actor_id == User.id)
        .where(AuditEvent.event_type == AuditEventType.USER_LOGIN)
        .order_by(desc(AuditEvent.timestamp))
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    logins = []
    for audit_event, user in rows:
        logins.append(LoginEventResponse(
            timestamp=audit_event.timestamp,
            username=user.username if user else "Unknown",
            user_id=audit_event.actor_id or "N/A",
            event_id=audit_event.id,
            correlation_id=audit_event.correlation_id
        ))

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=logins
    )

