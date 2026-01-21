"""Policy management API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.policy import PolicyCreate, PolicyResponse
from app.schemas.common import CorrelatedResponse
from app.services.policy import PolicyService
from app.api.deps import (
    get_correlation_id,
    get_current_user,
    get_policy_service,
    require_roles
)
from app.models.user import User, UserRole
from app.models.policy import PolicyType

router = APIRouter(prefix="/v1/policies", tags=["Policies"])


@router.post("", response_model=CorrelatedResponse[PolicyResponse])
async def create_policy(
    policy_data: PolicyCreate,
    db: AsyncSession = Depends(get_db),
    policy_service: PolicyService = Depends(get_policy_service),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    correlation_id: str = Depends(get_correlation_id)
):
    """Create a new policy rule."""
    policy = await policy_service.create_policy(
        policy_data,
        current_user.id,
        correlation_id
    )
    await db.commit()
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=PolicyResponse.model_validate(policy)
    )


@router.get("", response_model=CorrelatedResponse[List[PolicyResponse]])
async def list_policies(
    policy_type: Optional[PolicyType] = Query(None),
    is_active: bool = Query(True),
    limit: int = Query(100, le=1000),
    policy_service: PolicyService = Depends(get_policy_service),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.COMPLIANCE)),
    correlation_id: str = Depends(get_correlation_id)
):
    """List policies with optional filters."""
    policies = await policy_service.list_policies(
        policy_type=policy_type,
        is_active=is_active,
        limit=limit
    )
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=[PolicyResponse.model_validate(p) for p in policies]
    )


@router.get("/{policy_id}", response_model=CorrelatedResponse[PolicyResponse])
async def get_policy(
    policy_id: str,
    policy_service: PolicyService = Depends(get_policy_service),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.COMPLIANCE)),
    correlation_id: str = Depends(get_correlation_id)
):
    """Get policy by ID."""
    policy = await policy_service.get_policy(policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy {policy_id} not found"
        )
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=PolicyResponse.model_validate(policy)
    )

