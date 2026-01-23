"""KYT API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.services.kyt import KYTService, KYTResult
from app.services.audit import AuditService
from app.services.bitok_integration import get_bitok_integration, BitOKCheckResult
from app.config import get_settings


router = APIRouter(prefix="/kyt", tags=["kyt"])


# Request/Response schemas
class ManualAddressCheckRequest(BaseModel):
    """Request to manually check an address via BitOK."""
    network: str = Field(default="ETH", description="Network code (ETH, BTC, etc.)")
    address: str = Field(..., description="Address to check")


class ManualAddressCheckResponse(BaseModel):
    """Response from manual address check."""
    result: str = Field(..., description="Check result: ALLOW, REVIEW, BLOCK, UNCHECKED, ERROR")
    risk_level: Optional[str] = Field(None, description="BitOK risk level")
    check_id: Optional[int] = Field(None, description="BitOK check ID")
    exposure_direct: float = Field(0.0, description="Direct exposure percentage")
    exposure_indirect: float = Field(0.0, description="Indirect exposure percentage")
    risks: list = Field(default_factory=list, description="Identified risks")
    cached: bool = Field(False, description="Whether result was from cache")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class CacheStatsResponse(BaseModel):
    """Cache statistics."""
    total_entries: int
    valid_entries: int
    expired_entries: int
    ttl_hours: int


class CacheClearResponse(BaseModel):
    """Response from cache clear operation."""
    entries_cleared: int


class KYTStatusResponse(BaseModel):
    """KYT service status."""
    bitok_enabled: bool
    bitok_mock_mode: bool
    bitok_base_url: str
    fallback_on_error: bool
    cache_ttl_hours: int
    local_blacklist_count: int
    local_graylist_count: int


@router.post("/check-address", response_model=ManualAddressCheckResponse)
async def check_address(
    request: ManualAddressCheckRequest,
    current_user: dict = Depends(require_admin),
):
    """
    Manually check an address via BitOK KYT.

    This endpoint allows compliance officers to check any address
    before or after a transaction.
    """
    settings = get_settings()

    if not settings.bitok_enabled:
        raise HTTPException(
            status_code=400,
            detail="BitOK integration is not enabled"
        )

    bitok = get_bitok_integration()
    response = await bitok.check_address_outbound(
        network=request.network,
        address=request.address,
    )

    return ManualAddressCheckResponse(
        result=response.result.value,
        risk_level=response.risk_level,
        check_id=response.check_id,
        exposure_direct=response.exposure_direct,
        exposure_indirect=response.exposure_indirect,
        risks=response.risks,
        cached=response.cached,
        error_message=response.error_message,
    )


@router.get("/status", response_model=KYTStatusResponse)
async def get_kyt_status(
    current_user: dict = Depends(require_admin),
):
    """Get KYT service status and configuration."""
    settings = get_settings()

    return KYTStatusResponse(
        bitok_enabled=settings.bitok_enabled,
        bitok_mock_mode=settings.bitok_mock_mode,
        bitok_base_url=settings.bitok_base_url,
        fallback_on_error=settings.bitok_fallback_on_error,
        cache_ttl_hours=settings.bitok_cache_ttl_hours,
        local_blacklist_count=len(settings.kyt_blacklist_addresses),
        local_graylist_count=len(settings.kyt_graylist_addresses),
    )


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
    current_user: dict = Depends(require_admin),
):
    """Get BitOK KYT cache statistics."""
    bitok = get_bitok_integration()
    stats = bitok.get_cache_stats()

    return CacheStatsResponse(**stats)


@router.post("/cache/clear", response_model=CacheClearResponse)
async def clear_cache(
    current_user: dict = Depends(require_admin),
):
    """Clear BitOK KYT cache."""
    bitok = get_bitok_integration()
    count = bitok.clear_cache()

    return CacheClearResponse(entries_cleared=count)


@router.get("/cases")
async def list_cases(
    status: Optional[str] = None,
    direction: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """List KYT cases with optional filters."""
    audit = AuditService(db)
    kyt = KYTService(db, audit)
    cases = await kyt.list_cases(status=status, direction=direction, limit=limit)

    return [
        {
            "id": c.id,
            "address": c.address,
            "direction": c.direction,
            "reason": c.reason,
            "status": c.status,
            "resolved_by": c.resolved_by,
            "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
            "resolution_comment": c.resolution_comment,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in cases
    ]


@router.get("/cases/{case_id}")
async def get_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """Get KYT case details."""
    audit = AuditService(db)
    kyt = KYTService(db, audit)
    case = await kyt.get_case(case_id)

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return {
        "id": case.id,
        "address": case.address,
        "direction": case.direction,
        "reason": case.reason,
        "status": case.status,
        "resolved_by": case.resolved_by,
        "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
        "resolution_comment": case.resolution_comment,
        "created_at": case.created_at.isoformat() if case.created_at else None,
    }


class ResolveCaseRequest(BaseModel):
    """Request to resolve a KYT case."""
    decision: str = Field(..., description="ALLOW or BLOCK")
    comment: Optional[str] = Field(None, description="Resolution comment")


@router.post("/cases/{case_id}/resolve")
async def resolve_case(
    case_id: str,
    request: ResolveCaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """Resolve a pending KYT case."""
    if request.decision not in ["ALLOW", "BLOCK"]:
        raise HTTPException(
            status_code=400,
            detail="Decision must be ALLOW or BLOCK"
        )

    audit = AuditService(db)
    kyt = KYTService(db, audit)

    try:
        case = await kyt.resolve_case(
            case_id=case_id,
            decision=request.decision,
            resolved_by=current_user["sub"],
            correlation_id=f"kyt-resolve-{case_id}",
            comment=request.comment,
        )
        await db.commit()

        return {
            "id": case.id,
            "status": case.status,
            "resolved_by": case.resolved_by,
            "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
            "resolution_comment": case.resolution_comment,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
