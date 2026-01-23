"""API dependencies for dependency injection."""
from typing import Optional, List
from uuid import uuid4

from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.wallet import WalletService
from app.services.kyt import KYTService
from app.services.policy import PolicyService
from app.services.signing import SigningService
from app.services.ethereum import EthereumService
from app.services.orchestrator import TxOrchestrator
from app.services.mpc_coordinator import MPCCoordinator
from app.models.user import User, UserRole
from app.models.wallet import WalletRoleType

security = HTTPBearer()


def get_correlation_id(
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
) -> str:
    """Get or generate correlation ID for request tracing."""
    return x_correlation_id or str(uuid4())


def get_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
) -> Optional[str]:
    """Get idempotency key from header."""
    return idempotency_key


# Service dependencies

async def get_audit_service(db: AsyncSession = Depends(get_db)) -> AuditService:
    """Get audit service instance."""
    return AuditService(db)


async def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """Get auth service instance."""
    return AuthService(db)


async def get_wallet_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service)
) -> WalletService:
    """Get wallet service instance."""
    return WalletService(db, audit)


async def get_kyt_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service)
) -> KYTService:
    """Get KYT service instance."""
    return KYTService(db, audit)


async def get_policy_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service)
) -> PolicyService:
    """Get policy service instance."""
    return PolicyService(db, audit)


async def get_signing_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service)
) -> SigningService:
    """Get signing service instance."""
    return SigningService(db, audit)


async def get_ethereum_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service)
) -> EthereumService:
    """Get Ethereum service instance."""
    return EthereumService(db, audit)


async def get_mpc_coordinator(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service)
) -> MPCCoordinator:
    """Get MPC Coordinator instance."""
    return MPCCoordinator(db, audit)


async def get_orchestrator(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    kyt: KYTService = Depends(get_kyt_service),
    policy: PolicyService = Depends(get_policy_service),
    signing: SigningService = Depends(get_signing_service),
    ethereum: EthereumService = Depends(get_ethereum_service),
    mpc_coordinator: MPCCoordinator = Depends(get_mpc_coordinator)
) -> TxOrchestrator:
    """Get transaction orchestrator instance."""
    # Inject MPC coordinator into signing service
    signing.set_mpc_coordinator(mpc_coordinator)
    return TxOrchestrator(db, audit, kyt, policy, signing, ethereum, mpc_coordinator)


# Authentication dependencies

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth: AuthService = Depends(get_auth_service)
) -> User:
    """Get current authenticated user from JWT token."""
    payload = await auth.verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user = await auth.get_user_by_id(payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    return user


def require_roles(*roles: UserRole):
    """Dependency factory to require specific user roles."""
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {[r.value for r in roles]}"
            )
        return user
    return role_checker


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require user to be an admin."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


async def require_wallet_role(
    wallet_id: str,
    required_roles: List[WalletRoleType],
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service)
) -> User:
    """Check if user has required role on specific wallet."""
    # Admins bypass wallet-level checks
    if user.role == UserRole.ADMIN:
        return user
    
    has_permission = await auth.check_wallet_permission(
        user.id, wallet_id, required_roles
    )
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Required wallet roles: {[r.value for r in required_roles]}"
        )
    return user


async def get_current_user_ws(token: str) -> User:
    """
    Get current authenticated user from JWT token for WebSocket connections.
    
    Unlike the regular get_current_user, this accepts token directly
    since WebSocket doesn't use the same auth header mechanism.
    """
    from app.database import async_session_maker
    
    async with async_session_maker() as db:
        auth = AuthService(db)
        payload = await auth.verify_token(token)
        
        if not payload:
            raise ValueError("Invalid or expired token")
        
        user = await auth.get_user_by_id(payload["sub"])
        if not user or not user.is_active:
            raise ValueError("User not found or inactive")
        
        return user
