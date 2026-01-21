"""Unit tests for Policy Engine."""
import pytest
from decimal import Decimal
from uuid import uuid4

from app.models.wallet import Wallet, WalletType, RiskProfile
from app.models.tx_request import TxRequest, TxType, TxStatus
from app.models.policy import Policy, PolicyType
from app.services.audit import AuditService
from app.services.policy import PolicyService, PolicyEvalResult


@pytest.mark.asyncio
async def test_policy_address_denylist(db_session):
    """Test that address denylist blocks transactions."""
    audit = AuditService(db_session)
    policy_service = PolicyService(db_session, audit)
    
    # Create wallet
    wallet = Wallet(
        id=str(uuid4()),
        address="0x" + "1" * 40,
        wallet_type=WalletType.RETAIL,
        subject_id="user-123",
        risk_profile=RiskProfile.LOW,
        key_ref="test:key"
    )
    db_session.add(wallet)
    
    # Create denylist policy
    denied_address = "0x" + "d" * 40
    policy = Policy(
        id=str(uuid4()),
        name="Test Denylist",
        policy_type=PolicyType.ADDRESS_DENYLIST,
        address=denied_address.lower(),
        created_by=str(uuid4())
    )
    db_session.add(policy)
    await db_session.flush()
    
    # Create tx request to denied address
    tx = TxRequest(
        id=str(uuid4()),
        wallet_id=wallet.id,
        tx_type=TxType.TRANSFER,
        to_address=denied_address.lower(),
        asset="ETH",
        amount=Decimal("1.0"),
        status=TxStatus.POLICY_EVAL_PENDING,
        created_by=str(uuid4())
    )
    
    # Evaluate
    result = await policy_service.evaluate(
        tx, wallet, f"test-{uuid4()}"
    )
    
    assert not result.allowed
    assert result.blocked_by == "Test Denylist"
    assert "denylist" in result.reason.lower()


@pytest.mark.asyncio
async def test_policy_tx_limit(db_session):
    """Test that per-transaction limit blocks large transactions."""
    audit = AuditService(db_session)
    policy_service = PolicyService(db_session, audit)
    
    # Create wallet
    wallet = Wallet(
        id=str(uuid4()),
        address="0x" + "2" * 40,
        wallet_type=WalletType.RETAIL,
        subject_id="user-456",
        risk_profile=RiskProfile.LOW,
        key_ref="test:key"
    )
    db_session.add(wallet)
    
    # Create limit policy
    policy = Policy(
        id=str(uuid4()),
        name="TX Limit",
        policy_type=PolicyType.TX_LIMIT,
        wallet_type="RETAIL",
        limit_amount=Decimal("10.0"),
        created_by=str(uuid4())
    )
    db_session.add(policy)
    await db_session.flush()
    
    # Create tx request exceeding limit
    tx = TxRequest(
        id=str(uuid4()),
        wallet_id=wallet.id,
        tx_type=TxType.TRANSFER,
        to_address="0x" + "a" * 40,
        asset="ETH",
        amount=Decimal("15.0"),  # Exceeds limit
        status=TxStatus.POLICY_EVAL_PENDING,
        created_by=str(uuid4())
    )
    
    result = await policy_service.evaluate(
        tx, wallet, f"test-{uuid4()}"
    )
    
    assert not result.allowed
    assert result.blocked_by == "TX Limit"


@pytest.mark.asyncio
async def test_policy_treasury_approval_required(db_session):
    """Test that TREASURY wallets require approval by default."""
    audit = AuditService(db_session)
    policy_service = PolicyService(db_session, audit)
    
    # Create TREASURY wallet
    wallet = Wallet(
        id=str(uuid4()),
        address="0x" + "3" * 40,
        wallet_type=WalletType.TREASURY,
        subject_id="org-789",
        risk_profile=RiskProfile.HIGH,
        key_ref="test:key"
    )
    db_session.add(wallet)
    await db_session.flush()
    
    # Create tx request
    tx = TxRequest(
        id=str(uuid4()),
        wallet_id=wallet.id,
        tx_type=TxType.TRANSFER,
        to_address="0x" + "b" * 40,
        asset="ETH",
        amount=Decimal("1.0"),
        status=TxStatus.POLICY_EVAL_PENDING,
        created_by=str(uuid4())
    )
    
    result = await policy_service.evaluate(
        tx, wallet, f"test-{uuid4()}"
    )
    
    assert result.allowed
    assert result.requires_approval
    assert result.required_approvals == 2  # Default 2-of-3 for TREASURY


@pytest.mark.asyncio
async def test_policy_allows_valid_transaction(db_session):
    """Test that valid transactions are allowed."""
    audit = AuditService(db_session)
    policy_service = PolicyService(db_session, audit)
    
    # Create wallet
    wallet = Wallet(
        id=str(uuid4()),
        address="0x" + "4" * 40,
        wallet_type=WalletType.RETAIL,
        subject_id="user-101",
        risk_profile=RiskProfile.LOW,
        key_ref="test:key"
    )
    db_session.add(wallet)
    await db_session.flush()
    
    # Create tx request
    tx = TxRequest(
        id=str(uuid4()),
        wallet_id=wallet.id,
        tx_type=TxType.TRANSFER,
        to_address="0x" + "c" * 40,
        asset="ETH",
        amount=Decimal("1.0"),
        status=TxStatus.POLICY_EVAL_PENDING,
        created_by=str(uuid4())
    )
    
    result = await policy_service.evaluate(
        tx, wallet, f"test-{uuid4()}"
    )
    
    assert result.allowed
    assert not result.requires_approval  # RETAIL doesn't require approval by default

