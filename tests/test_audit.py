"""Unit tests for Audit hash chain."""
import pytest
from uuid import uuid4

from app.models.audit import AuditEvent, AuditEventType
from app.services.audit import AuditService


@pytest.mark.asyncio
async def test_audit_hash_chain_integrity(db_session):
    """Test that audit events form a valid hash chain."""
    audit = AuditService(db_session)
    correlation_id = f"test-{uuid4()}"
    
    # Create multiple events
    events = []
    for i in range(5):
        event = await audit.log_event(
            event_type=AuditEventType.WALLET_CREATED,
            correlation_id=correlation_id,
            actor_id=str(uuid4()),
            entity_type="WALLET",
            entity_id=str(uuid4()),
            payload={"index": i}
        )
        events.append(event)
    
    await db_session.commit()
    
    # Verify chain
    result = await audit.verify_chain()
    
    assert result.is_valid
    assert result.chain_intact
    assert result.total_events == 5
    assert result.verified_events == 5
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_audit_hash_chain_prev_hash(db_session):
    """Test that each event references the previous event's hash."""
    audit = AuditService(db_session)
    correlation_id = f"test-{uuid4()}"
    
    # Create first event
    event1 = await audit.log_event(
        event_type=AuditEventType.TX_REQUEST_CREATED,
        correlation_id=correlation_id,
        actor_id=str(uuid4()),
        entity_type="TX_REQUEST",
        entity_id=str(uuid4()),
        payload={"test": 1}
    )
    
    # First event should have no prev_hash
    assert event1.prev_hash is None
    assert event1.hash is not None
    
    # Create second event
    event2 = await audit.log_event(
        event_type=AuditEventType.TX_STATUS_CHANGED,
        correlation_id=correlation_id,
        actor_id=str(uuid4()),
        entity_type="TX_REQUEST",
        entity_id=str(uuid4()),
        payload={"test": 2}
    )
    
    # Second event should reference first event's hash
    assert event2.prev_hash == event1.hash
    assert event2.hash is not None
    assert event2.hash != event1.hash


@pytest.mark.asyncio
async def test_audit_hash_computation(db_session):
    """Test that hash is computed correctly and is deterministic."""
    from datetime import datetime
    
    event_id = str(uuid4())
    timestamp = datetime(2024, 1, 15, 12, 0, 0)
    
    hash1 = AuditEvent.compute_hash(
        event_id=event_id,
        timestamp=timestamp,
        event_type="WALLET_CREATED",
        actor_id="actor-123",
        entity_type="WALLET",
        entity_id="wallet-456",
        payload={"key": "value"},
        prev_hash="abc123"
    )
    
    # Same inputs should produce same hash
    hash2 = AuditEvent.compute_hash(
        event_id=event_id,
        timestamp=timestamp,
        event_type="WALLET_CREATED",
        actor_id="actor-123",
        entity_type="WALLET",
        entity_id="wallet-456",
        payload={"key": "value"},
        prev_hash="abc123"
    )
    
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 produces 64 hex characters
    
    # Different input should produce different hash
    hash3 = AuditEvent.compute_hash(
        event_id=event_id,
        timestamp=timestamp,
        event_type="WALLET_CREATED",
        actor_id="actor-123",
        entity_type="WALLET",
        entity_id="wallet-456",
        payload={"key": "different"},  # Changed payload
        prev_hash="abc123"
    )
    
    assert hash3 != hash1

