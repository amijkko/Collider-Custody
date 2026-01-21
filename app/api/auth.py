"""Authentication API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import UserCreate, UserLogin, TokenResponse, UserResponse
from app.schemas.common import CorrelatedResponse
from app.services.auth import AuthService
from app.services.audit import AuditService
from app.models.audit import AuditEventType
from app.api.deps import get_correlation_id, get_current_user
from app.models.user import User

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=CorrelatedResponse[UserResponse])
async def register_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id)
):
    """Register a new user."""
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    
    try:
        user = await auth_service.create_user(user_data)
        await db.commit()
        
        return CorrelatedResponse(
            correlation_id=correlation_id,
            data=UserResponse.model_validate(user)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.post("/login", response_model=CorrelatedResponse[TokenResponse])
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
    correlation_id: str = Depends(get_correlation_id)
):
    """Authenticate user and return JWT token."""
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    
    user = await auth_service.authenticate(credentials.username, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    token = auth_service.create_token(user)
    
    # Log login event
    await audit_service.log_event(
        event_type=AuditEventType.USER_LOGIN,
        correlation_id=correlation_id,
        actor_id=user.id,
        entity_type="USER",
        entity_id=user.id,
        payload={"username": user.username}
    )
    await db.commit()
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=token
    )


@router.get("/me", response_model=CorrelatedResponse[UserResponse])
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id)
):
    """Get current authenticated user info."""
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=UserResponse.model_validate(current_user)
    )

