"""KYT Cases API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.tx_request import KYTCaseResponse, KYTCaseResolve
from app.schemas.common import CorrelatedResponse
from app.services.kyt import KYTService
from app.api.deps import (
    get_correlation_id,
    get_current_user,
    get_kyt_service,
    require_roles
)
from app.models.user import User, UserRole

router = APIRouter(prefix="/v1/cases", tags=["KYT Cases"])


@router.get("", response_model=CorrelatedResponse[List[KYTCaseResponse]])
async def list_cases(
    status: Optional[str] = Query(None, description="Filter by status: PENDING, RESOLVED_ALLOW, RESOLVED_BLOCK"),
    direction: Optional[str] = Query(None, description="Filter by direction: INBOUND, OUTBOUND"),
    limit: int = Query(100, le=1000),
    kyt_service: KYTService = Depends(get_kyt_service),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.COMPLIANCE)),
    correlation_id: str = Depends(get_correlation_id)
):
    """List KYT cases with optional filters."""
    cases = await kyt_service.list_cases(
        status=status,
        direction=direction,
        limit=limit
    )
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=[KYTCaseResponse.model_validate(c) for c in cases]
    )


@router.get("/{case_id}", response_model=CorrelatedResponse[KYTCaseResponse])
async def get_case(
    case_id: str,
    kyt_service: KYTService = Depends(get_kyt_service),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.COMPLIANCE)),
    correlation_id: str = Depends(get_correlation_id)
):
    """Get KYT case by ID."""
    case = await kyt_service.get_case(case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found"
        )
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=KYTCaseResponse.model_validate(case)
    )


@router.post("/{case_id}/resolve", response_model=CorrelatedResponse[KYTCaseResponse])
async def resolve_case(
    case_id: str,
    resolution: KYTCaseResolve,
    db: AsyncSession = Depends(get_db),
    kyt_service: KYTService = Depends(get_kyt_service),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.COMPLIANCE)),
    correlation_id: str = Depends(get_correlation_id)
):
    """
    Resolve a pending KYT case.
    
    Decision must be ALLOW or BLOCK.
    After resolution, associated transaction (if any) can be resumed.
    """
    try:
        case = await kyt_service.resolve_case(
            case_id,
            resolution.decision,
            current_user.id,
            correlation_id,
            resolution.comment
        )
        await db.commit()
        
        return CorrelatedResponse(
            correlation_id=correlation_id,
            data=KYTCaseResponse.model_validate(case)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

