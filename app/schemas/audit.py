"""Audit schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from app.models.audit import AuditEventType


class AuditEventResponse(BaseModel):
    """Schema for audit event response."""
    id: str
    sequence_number: int
    timestamp: datetime
    event_type: AuditEventType
    actor_id: Optional[str]
    actor_type: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    entity_refs: Optional[dict]
    payload: Optional[dict]
    correlation_id: str
    prev_hash: Optional[str]
    hash: str
    
    class Config:
        from_attributes = True


class AuditPackageResponse(BaseModel):
    """Schema for audit package - aggregated audit trail for a tx request."""
    tx_request_id: str
    tx_request: dict
    policy_evaluation: Optional[dict]
    kyt_evaluation: Optional[dict]
    approvals: List[dict]
    signing: Optional[dict]
    broadcast: Optional[dict]
    confirmations: Optional[dict]
    audit_events: List[AuditEventResponse]
    package_hash: str  # Hash of the entire package for verification
    generated_at: datetime


class AuditVerifyResponse(BaseModel):
    """Schema for audit verification response."""
    is_valid: bool
    total_events: int
    verified_events: int
    first_event_id: Optional[str]
    last_event_id: Optional[str]
    chain_intact: bool
    errors: List[str] = []

