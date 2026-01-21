"""Authentication service with JWT."""
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User, UserRole
from app.models.wallet import WalletRole, WalletRoleType
from app.schemas.auth import UserCreate, TokenResponse


settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for authentication and authorization."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        # Check if user exists
        existing = await self.db.execute(
            select(User).where(
                (User.username == user_data.username) | 
                (User.email == user_data.email)
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("User with this username or email already exists")
        
        # bcrypt has 72 byte limit, truncate if needed
        password = user_data.password[:72]
        
        user = User(
            id=str(uuid4()),
            username=user_data.username,
            email=user_data.email,
            password_hash=pwd_context.hash(password),
            role=user_data.role
        )
        
        self.db.add(user)
        await self.db.flush()
        
        return user
    
    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password."""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            return None
        
        # bcrypt has 72 byte limit, truncate for consistency
        if not pwd_context.verify(password[:72], user.password_hash):
            return None
        
        return user
    
    def create_token(self, user: User) -> TokenResponse:
        """Create JWT token for user."""
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
        
        payload = {
            "sub": user.id,
            "username": user.username,
            "role": user.role.value,
            "exp": expire
        }
        
        token = jwt.encode(
            payload,
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm
        )
        
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.jwt_expire_minutes * 60,
            user_id=user.id,
            username=user.username,
            role=user.role
        )
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def verify_token(self, token: str) -> Optional[dict]:
        """Verify JWT token and return payload."""
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm]
            )
            return payload
        except JWTError:
            return None
    
    async def get_wallet_roles(
        self,
        user_id: str,
        wallet_id: str
    ) -> List[WalletRoleType]:
        """Get user's roles on a specific wallet."""
        result = await self.db.execute(
            select(WalletRole)
            .where(WalletRole.user_id == user_id)
            .where(WalletRole.wallet_id == wallet_id)
        )
        roles = result.scalars().all()
        return [r.role for r in roles]
    
    async def check_wallet_permission(
        self,
        user_id: str,
        wallet_id: str,
        required_roles: List[WalletRoleType]
    ) -> bool:
        """Check if user has required role on wallet."""
        user_roles = await self.get_wallet_roles(user_id, wallet_id)
        return any(role in required_roles for role in user_roles)
    
    async def is_admin(self, user_id: str) -> bool:
        """Check if user is admin."""
        user = await self.get_user_by_id(user_id)
        return user and user.role == UserRole.ADMIN

