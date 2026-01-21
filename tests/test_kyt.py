"""Unit tests for KYT service."""
import pytest
from uuid import uuid4

from app.config import get_settings
from app.services.audit import AuditService
from app.services.kyt import KYTService, KYTResult


@pytest.mark.asyncio
async def test_kyt_blocks_blacklisted_address(db_session, monkeypatch):
    """Test that blacklisted addresses are blocked."""
    # Configure blacklist
    monkeypatch.setenv("KYT_BLACKLIST", "0xbad0000000000000000000000000000000000bad")
    
    # Clear cached settings
    from app.config import get_settings
    get_settings.cache_clear()
    
    audit = AuditService(db_session)
    kyt = KYTService(db_session, audit)
    
    tx_request_id = str(uuid4())
    correlation_id = f"test-{uuid4()}"
    
    result, case = await kyt.evaluate_outbound(
        "0xbad0000000000000000000000000000000000bad",
        tx_request_id,
        correlation_id
    )
    
    assert result == KYTResult.BLOCK
    assert case is None  # No case created for BLOCK


@pytest.mark.asyncio
async def test_kyt_flags_graylist_for_review(db_session, monkeypatch):
    """Test that graylisted addresses create a review case."""
    # Configure graylist
    monkeypatch.setenv("KYT_GRAYLIST", "0x1234567890123456789012345678901234567890")
    monkeypatch.setenv("KYT_BLACKLIST", "")
    
    from app.config import get_settings
    get_settings.cache_clear()
    
    audit = AuditService(db_session)
    kyt = KYTService(db_session, audit)
    
    tx_request_id = str(uuid4())
    correlation_id = f"test-{uuid4()}"
    
    result, case = await kyt.evaluate_outbound(
        "0x1234567890123456789012345678901234567890",
        tx_request_id,
        correlation_id
    )
    
    assert result == KYTResult.REVIEW
    assert case is not None
    assert case.status == "PENDING"
    assert case.direction == "OUTBOUND"


@pytest.mark.asyncio
async def test_kyt_allows_clean_address(db_session, monkeypatch):
    """Test that clean addresses are allowed."""
    monkeypatch.setenv("KYT_BLACKLIST", "")
    monkeypatch.setenv("KYT_GRAYLIST", "")
    
    from app.config import get_settings
    get_settings.cache_clear()
    
    audit = AuditService(db_session)
    kyt = KYTService(db_session, audit)
    
    tx_request_id = str(uuid4())
    correlation_id = f"test-{uuid4()}"
    
    result, case = await kyt.evaluate_outbound(
        "0xabcdef0123456789abcdef0123456789abcdef01",
        tx_request_id,
        correlation_id
    )
    
    assert result == KYTResult.ALLOW
    assert case is None


@pytest.mark.asyncio
async def test_kyt_case_resolution(db_session, monkeypatch):
    """Test KYT case resolution flow."""
    monkeypatch.setenv("KYT_GRAYLIST", "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setenv("KYT_BLACKLIST", "")
    
    from app.config import get_settings
    get_settings.cache_clear()
    
    audit = AuditService(db_session)
    kyt = KYTService(db_session, audit)
    
    tx_request_id = str(uuid4())
    correlation_id = f"test-{uuid4()}"
    resolver_id = str(uuid4())
    
    # Create case
    result, case = await kyt.evaluate_outbound(
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        tx_request_id,
        correlation_id
    )
    
    assert case is not None
    assert case.status == "PENDING"
    
    # Resolve case
    resolved_case = await kyt.resolve_case(
        case.id,
        "ALLOW",
        resolver_id,
        correlation_id,
        "Manual review completed, address is legitimate"
    )
    
    assert resolved_case.status == "RESOLVED_ALLOW"
    assert resolved_case.resolved_by == resolver_id
    assert resolved_case.resolved_at is not None
    assert "legitimate" in resolved_case.resolution_comment

