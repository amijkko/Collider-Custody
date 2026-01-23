"""Group and Policy schemas for API."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from app.models.group import AddressKind
from app.models.policy_set import PolicyDecision


# ============== Group Schemas ==============

class GroupCreate(BaseModel):
    """Create a new group."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    is_default: bool = False


class GroupUpdate(BaseModel):
    """Update group details."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class GroupMemberResponse(BaseModel):
    """Group member info."""
    user_id: str
    username: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class GroupResponse(BaseModel):
    """Group details."""
    id: str
    name: str
    description: Optional[str]
    is_default: bool
    member_count: int = 0
    allowlist_count: int = 0
    denylist_count: int = 0
    policy_set_id: Optional[str] = None
    policy_set_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GroupListResponse(BaseModel):
    """List of groups."""
    groups: List[GroupResponse]
    total: int


# ============== Address Book Schemas ==============

class AddressBookEntryCreate(BaseModel):
    """Add address to address book."""
    address: str = Field(..., pattern=r"^0x[a-fA-F0-9]{40}$")
    kind: AddressKind
    label: Optional[str] = Field(None, max_length=255)


class AddressBookEntryResponse(BaseModel):
    """Address book entry."""
    id: str
    address: str
    kind: AddressKind
    label: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AddressBookListResponse(BaseModel):
    """List of address book entries."""
    entries: List[AddressBookEntryResponse]
    total: int
    allowlist_count: int
    denylist_count: int


class AddressCheckResponse(BaseModel):
    """Result of checking an address."""
    address: str
    status: str  # 'allowlist', 'denylist', 'unknown'
    label: Optional[str]


# ============== Policy Set Schemas ==============

class PolicyRuleResponse(BaseModel):
    """Policy rule details."""
    id: str
    rule_id: str
    priority: int
    conditions: dict
    decision: PolicyDecision
    kyt_required: bool
    approval_required: bool
    approval_count: int
    description: Optional[str]

    model_config = {"from_attributes": True}


class PolicySetResponse(BaseModel):
    """Policy set details."""
    id: str
    name: str
    version: int
    description: Optional[str]
    is_active: bool
    snapshot_hash: Optional[str]
    rules: List[PolicyRuleResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicySetListResponse(BaseModel):
    """List of policy sets."""
    policy_sets: List[PolicySetResponse]
    total: int


class PolicyAssignRequest(BaseModel):
    """Assign policy to group."""
    policy_set_id: str


class PolicyEvalPreviewRequest(BaseModel):
    """Preview policy evaluation for an address."""
    to_address: str = Field(..., pattern=r"^0x[a-fA-F0-9]{40}$")
    amount: str  # Wei as string
    asset: str = "ETH"


class PolicyEvalPreviewResponse(BaseModel):
    """Policy evaluation preview result."""
    decision: str
    allowed: bool
    matched_rules: List[str]
    reasons: List[str]
    kyt_required: bool
    approval_required: bool
    approval_count: int
    address_status: str
    address_label: Optional[str]
    policy_version: str
