"""API routers package."""
from app.api.auth import router as auth_router
from app.api.wallets import router as wallets_router
from app.api.tx_requests import router as tx_requests_router
from app.api.cases import router as cases_router
from app.api.policies import router as policies_router
from app.api.audit import router as audit_router

__all__ = [
    "auth_router",
    "wallets_router",
    "tx_requests_router",
    "cases_router",
    "policies_router",
    "audit_router",
]

