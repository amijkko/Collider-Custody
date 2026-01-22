"""Wallet management API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.wallet import (
    WalletCreate, WalletResponse, WalletRoleAssign, WalletRoleResponse,
    WalletCreateMPC, MPCKeysetResponse
)
from app.schemas.common import CorrelatedResponse
from app.services.wallet import WalletService
from app.api.deps import (
    get_correlation_id,
    get_idempotency_key,
    get_current_user,
    get_wallet_service,
    get_mpc_coordinator,
    get_ethereum_service,
    require_roles
)
from app.services.ethereum import EthereumService
from pydantic import BaseModel
from app.models.user import User, UserRole
from app.models.wallet import WalletType, CustodyBackend
from app.services.mpc_coordinator import MPCCoordinator

router = APIRouter(prefix="/v1/wallets", tags=["Wallets"])


@router.post("", response_model=CorrelatedResponse[WalletResponse])
async def create_wallet(
    wallet_data: WalletCreate,
    db: AsyncSession = Depends(get_db),
    wallet_service: WalletService = Depends(get_wallet_service),
    current_user: User = Depends(get_current_user),  # Allow any authenticated user (demo mode)
    correlation_id: str = Depends(get_correlation_id),
    idempotency_key: Optional[str] = Depends(get_idempotency_key)
):
    """
    Create a new Ethereum wallet (EOA).
    
    Supports idempotency via Idempotency-Key header.
    """
    wallet = await wallet_service.create_wallet(
        wallet_data,
        current_user.id,
        correlation_id,
        idempotency_key
    )
    await db.commit()
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=WalletResponse.model_validate(wallet)
    )


@router.get("", response_model=CorrelatedResponse[List[WalletResponse]])
async def list_wallets(
    wallet_type: Optional[WalletType] = Query(None),
    subject_id: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    wallet_service: WalletService = Depends(get_wallet_service),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id)
):
    """List wallets with optional filters."""
    wallets = await wallet_service.list_wallets(
        wallet_type=wallet_type,
        subject_id=subject_id,
        limit=limit,
        offset=offset
    )
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=[WalletResponse.model_validate(w) for w in wallets]
    )


@router.get("/{wallet_id}", response_model=CorrelatedResponse[WalletResponse])
async def get_wallet(
    wallet_id: str,
    wallet_service: WalletService = Depends(get_wallet_service),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id)
):
    """Get wallet by ID."""
    wallet = await wallet_service.get_wallet(wallet_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallet {wallet_id} not found"
        )
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=WalletResponse.model_validate(wallet)
    )


@router.post("/{wallet_id}/roles", response_model=CorrelatedResponse[WalletRoleResponse])
async def assign_wallet_role(
    wallet_id: str,
    role_data: WalletRoleAssign,
    db: AsyncSession = Depends(get_db),
    wallet_service: WalletService = Depends(get_wallet_service),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    correlation_id: str = Depends(get_correlation_id)
):
    """Assign a role to a user on a wallet."""
    # Verify wallet exists
    wallet = await wallet_service.get_wallet(wallet_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallet {wallet_id} not found"
        )
    
    role = await wallet_service.assign_role(
        wallet_id,
        role_data,
        current_user.id,
        correlation_id
    )
    await db.commit()
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=WalletRoleResponse.model_validate(role)
    )


@router.delete("/{wallet_id}/roles/{user_id}", response_model=CorrelatedResponse[dict])
async def revoke_wallet_role(
    wallet_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    wallet_service: WalletService = Depends(get_wallet_service),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    correlation_id: str = Depends(get_correlation_id)
):
    """Revoke a user's role on a wallet."""
    success = await wallet_service.revoke_role(
        wallet_id,
        user_id,
        current_user.id,
        correlation_id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    await db.commit()
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data={"message": "Role revoked successfully"}
    )


# ============== MPC Wallet Endpoints ==============

@router.post("/mpc", response_model=CorrelatedResponse[WalletResponse], tags=["MPC"])
async def create_mpc_wallet(
    wallet_data: WalletCreateMPC,
    db: AsyncSession = Depends(get_db),
    wallet_service: WalletService = Depends(get_wallet_service),
    mpc_coordinator: MPCCoordinator = Depends(get_mpc_coordinator),
    current_user: User = Depends(get_current_user),  # Allow any authenticated user (demo mode)
    correlation_id: str = Depends(get_correlation_id),
    idempotency_key: Optional[str] = Depends(get_idempotency_key)
):
    """
    Create a new MPC wallet via tECDSA DKG.
    
    This endpoint:
    1. Creates a wallet record in PENDING_KEYGEN state
    2. Initiates Distributed Key Generation (DKG) via MPC Coordinator
    3. Returns the wallet with the derived EOA address
    
    No full private key ever exists - only threshold shares on MPC nodes.
    
    Parameters:
    - wallet_type: Type of wallet (RETAIL/TREASURY/OPS/SETTLEMENT)
    - subject_id: Owner/organization identifier
    - mpc_threshold_t: Minimum signatures required (default: 2)
    - mpc_total_n: Total number of parties (default: 3)
    """
    # Inject MPC coordinator into wallet service
    wallet_service.set_mpc_coordinator(mpc_coordinator)
    
    wallet = await wallet_service.create_mpc_wallet(
        wallet_data,
        current_user.id,
        correlation_id,
        idempotency_key
    )
    await db.commit()
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=WalletResponse.model_validate(wallet)
    )


@router.get("/{wallet_id}/mpc", response_model=CorrelatedResponse[MPCKeysetResponse], tags=["MPC"])
async def get_wallet_mpc_info(
    wallet_id: str,
    wallet_service: WalletService = Depends(get_wallet_service),
    mpc_coordinator: MPCCoordinator = Depends(get_mpc_coordinator),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    correlation_id: str = Depends(get_correlation_id)
):
    """
    Get MPC keyset information for a wallet.
    
    Returns detailed information about the MPC keyset including:
    - Threshold parameters (t-of-n)
    - Public key
    - Keyset status
    - Last usage timestamp
    """
    wallet = await wallet_service.get_wallet(wallet_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallet {wallet_id} not found"
        )
    
    if wallet.custody_backend != CustodyBackend.MPC_TECDSA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Wallet {wallet_id} is not an MPC wallet"
        )
    
    if not wallet.mpc_keyset_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No keyset found for wallet {wallet_id}"
        )
    
    keyset = await mpc_coordinator.get_keyset(wallet.mpc_keyset_id)
    if not keyset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Keyset {wallet.mpc_keyset_id} not found"
        )
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=MPCKeysetResponse.model_validate(keyset)
    )


class WalletBalanceResponse(BaseModel):
    """Wallet balance response."""
    wallet_id: str
    address: str
    balance_eth: str
    balance_wei: str


@router.get("/{wallet_id}/balance", response_model=CorrelatedResponse[WalletBalanceResponse])
async def get_wallet_balance(
    wallet_id: str,
    wallet_service: WalletService = Depends(get_wallet_service),
    ethereum: EthereumService = Depends(get_ethereum_service),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id)
):
    """
    Get the ETH balance of a wallet.
    
    Returns the balance in both ETH and wei.
    """
    wallet = await wallet_service.get_wallet(wallet_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallet {wallet_id} not found"
        )
    
    if not wallet.address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Wallet {wallet_id} has no address"
        )
    
    balance = await ethereum.get_balance(wallet.address)
    balance_wei = int(balance * 10**18)
    
    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=WalletBalanceResponse(
            wallet_id=wallet_id,
            address=wallet.address,
            balance_eth=str(balance),
            balance_wei=str(balance_wei)
        )
    )

