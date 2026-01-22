"""Main FastAPI application."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi

from app.config import get_settings
from app.database import async_session_maker
from app.api import (
    auth_router,
    wallets_router,
    tx_requests_router,
    cases_router,
    policies_router,
    audit_router,
)
from app.api.deposits import router as deposits_router
from app.api.mpc_websocket import router as mpc_ws_router
from app.services.chain_listener import ChainListener

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Global chain listener instance
chain_listener: Optional[ChainListener] = None
chain_listener_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global chain_listener, chain_listener_task
    
    logger.info("Starting Collider Custody Service...")
    
    # Start chain listener in background
    # Chain listener monitors blockchain for confirmations and inbound deposits
    chain_listener = ChainListener(
        session_maker=async_session_maker,
        poll_interval=settings.chain_listener_poll_interval
    )
    chain_listener_task = asyncio.create_task(chain_listener.start())
    logger.info("Chain listener started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    if chain_listener:
        await chain_listener.stop()
    if chain_listener_task:
        chain_listener_task.cancel()
        try:
            await chain_listener_task
        except asyncio.CancelledError:
            pass
    
    logger.info("Shutdown complete")


app = FastAPI(
    title="Collider Custody - Transaction Security Layer",
    description="""
## On-prem Transaction Security Layer + Wallet-as-a-Service (Ethereum)

This API provides enterprise-grade custody and transaction management for Ethereum:

### Features
- **Wallet Registry**: Create and manage Ethereum wallets with role-based access
- **Transaction Orchestrator**: State machine for transaction lifecycle
- **KYT (Know Your Transaction)**: Screen transactions against blacklists/graylists
- **Policy Engine**: Enforce limits, denylists, and approval requirements
- **Approvals**: Segregation of Duties with multi-approval workflows
- **Signing**: Dev mode signer (HSM/MPC interface ready)
- **Chain Listener**: Monitor confirmations and inbound deposits
- **Audit Log**: Tamper-evident hash-chain audit trail

### Security
- JWT-based authentication with RBAC
- Wallet-scoped permissions
- Idempotent operations
- Complete audit trail
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
# Get allowed origins from environment or use defaults
def get_allowed_origins():
    """Get allowed CORS origins from environment or defaults."""
    env_origins = os.getenv("CORS_ORIGINS", "")
    if env_origins:
        return [origin.strip() for origin in env_origins.split(",") if origin.strip()]
    
    # Default origins for development
    default_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ]
    
    # Add Vercel preview and production URLs if available
    vercel_url = os.getenv("VERCEL_URL")
    if vercel_url:
        default_origins.append(f"https://{vercel_url}")
    
    # Add custom production domain if set
    prod_domain = os.getenv("PRODUCTION_DOMAIN")
    if prod_domain:
        default_origins.append(f"https://{prod_domain}")
        default_origins.append(f"https://www.{prod_domain}")
    
    return default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "correlation_id": request.headers.get("X-Correlation-ID", "unknown"),
            "error": "Internal server error",
            "error_code": "INTERNAL_ERROR"
        }
    )


# Include routers
app.include_router(auth_router)
app.include_router(wallets_router)
app.include_router(tx_requests_router)
app.include_router(cases_router)
app.include_router(policies_router)
app.include_router(audit_router)
app.include_router(deposits_router)
app.include_router(mpc_ws_router, tags=["MPC WebSocket"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "chain_listener_running": chain_listener is not None and chain_listener._running
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Collider Custody API",
        "version": "1.0.0",
        "docs": "/docs",
        "openapi": "/openapi.json"
    }


def custom_openapi():
    """Generate custom OpenAPI schema."""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    
    # Add global headers
    openapi_schema["components"]["parameters"] = {
        "CorrelationId": {
            "name": "X-Correlation-ID",
            "in": "header",
            "required": False,
            "schema": {"type": "string"},
            "description": "Request correlation ID for tracing"
        },
        "IdempotencyKey": {
            "name": "Idempotency-Key",
            "in": "header",
            "required": False,
            "schema": {"type": "string"},
            "description": "Idempotency key for POST requests"
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

