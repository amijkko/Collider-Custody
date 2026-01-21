"""Unit tests for Segregation of Duties (SoD) enforcement."""
import pytest
from decimal import Decimal
from uuid import uuid4

from app.models.user import User, UserRole
from app.models.wallet import Wallet, WalletType, RiskProfile
from app.models.tx_request import TxRequest, TxType, TxStatus, Approval
from app.services.auth import pwd_context
from app.services.audit import AuditService
from app.services.kyt import KYTService
from app.services.policy import PolicyService
from app.services.signing import SigningService
from app.services.ethereum import EthereumService
from app.services.orchestrator import TxOrchestrator


@pytest.mark.asyncio
async def test_sod_creator_cannot_approve(db_session):
    """Test that transaction creator cannot approve their own transaction."""
    # Create users
    creator_id = str(uuid4())
    approver_id = str(uuid4())
    
    creator = User(
        id=creator_id,
        username="creator",
        email="creator@example.com",
        password_hash=pwd_context.hash("password"),
        role=UserRole.OPERATOR
    )
    approver = User(
        id=approver_id,
        username="approver",
        email="approver@example.com",
        password_hash=pwd_context.hash("password"),
        role=UserRole.OPERATOR
    )
    db_session.add_all([creator, approver])
    
    # Create wallet
    wallet = Wallet(
        id=str(uuid4()),
        address="0x" + "1" * 40,
        wallet_type=WalletType.TREASURY,
        subject_id="org-123",
        risk_profile=RiskProfile.HIGH,
        key_ref="test:key"
    )
    db_session.add(wallet)
    
    # Create tx request (created by creator)
    tx = TxRequest(
        id=str(uuid4()),
        wallet_id=wallet.id,
        tx_type=TxType.TRANSFER,
        to_address="0x" + "a" * 40,
        asset="ETH",
        amount=Decimal("1.0"),
        status=TxStatus.APPROVAL_PENDING,
        requires_approval=True,
        required_approvals=2,
        created_by=creator_id
    )
    db_session.add(tx)
    await db_session.flush()
    
    # Initialize services
    audit = AuditService(db_session)
    kyt = KYTService(db_session, audit)
    policy = PolicyService(db_session, audit)
    signing = SigningService(db_session, audit)
    ethereum = EthereumService(db_session, audit)
    orchestrator = TxOrchestrator(db_session, audit, kyt, policy, signing, ethereum)
    
    # Try to have creator approve their own tx - should fail
    with pytest.raises(ValueError) as exc_info:
        await orchestrator.process_approval(
            tx.id,
            creator_id,  # Creator trying to approve
            "APPROVED",
            "Self-approval attempt",
            f"test-{uuid4()}"
        )
    
    assert "Segregation of Duties" in str(exc_info.value)
    assert "creator cannot be approver" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sod_different_user_can_approve(db_session):
    """Test that a different user can approve a transaction."""
    # Create users
    creator_id = str(uuid4())
    approver_id = str(uuid4())
    
    creator = User(
        id=creator_id,
        username="creator2",
        email="creator2@example.com",
        password_hash=pwd_context.hash("password"),
        role=UserRole.OPERATOR
    )
    approver = User(
        id=approver_id,
        username="approver2",
        email="approver2@example.com",
        password_hash=pwd_context.hash("password"),
        role=UserRole.OPERATOR
    )
    db_session.add_all([creator, approver])
    
    # Create wallet
    wallet = Wallet(
        id=str(uuid4()),
        address="0x" + "2" * 40,
        wallet_type=WalletType.TREASURY,
        subject_id="org-456",
        risk_profile=RiskProfile.HIGH,
        key_ref="test:key"
    )
    db_session.add(wallet)
    
    # Create tx request
    tx = TxRequest(
        id=str(uuid4()),
        wallet_id=wallet.id,
        tx_type=TxType.TRANSFER,
        to_address="0x" + "b" * 40,
        asset="ETH",
        amount=Decimal("1.0"),
        status=TxStatus.APPROVAL_PENDING,
        requires_approval=True,
        required_approvals=2,
        created_by=creator_id
    )
    db_session.add(tx)
    await db_session.flush()
    
    # Initialize services
    audit = AuditService(db_session)
    kyt = KYTService(db_session, audit)
    policy = PolicyService(db_session, audit)
    signing = SigningService(db_session, audit)
    ethereum = EthereumService(db_session, audit)
    orchestrator = TxOrchestrator(db_session, audit, kyt, policy, signing, ethereum)
    
    # Different user approves - should succeed
    tx_result, approval = await orchestrator.process_approval(
        tx.id,
        approver_id,  # Different user approving
        "APPROVED",
        "Looks good",
        f"test-{uuid4()}"
    )
    
    assert approval.decision == "APPROVED"
    assert approval.user_id == approver_id


@pytest.mark.asyncio
async def test_sod_no_double_voting(db_session):
    """Test that a user cannot vote twice on the same transaction."""
    # Create users
    creator_id = str(uuid4())
    approver_id = str(uuid4())
    
    creator = User(
        id=creator_id,
        username="creator3",
        email="creator3@example.com",
        password_hash=pwd_context.hash("password"),
        role=UserRole.OPERATOR
    )
    approver = User(
        id=approver_id,
        username="approver3",
        email="approver3@example.com",
        password_hash=pwd_context.hash("password"),
        role=UserRole.OPERATOR
    )
    db_session.add_all([creator, approver])
    
    # Create wallet
    wallet = Wallet(
        id=str(uuid4()),
        address="0x" + "3" * 40,
        wallet_type=WalletType.TREASURY,
        subject_id="org-789",
        risk_profile=RiskProfile.HIGH,
        key_ref="test:key"
    )
    db_session.add(wallet)
    
    # Create tx request
    tx = TxRequest(
        id=str(uuid4()),
        wallet_id=wallet.id,
        tx_type=TxType.TRANSFER,
        to_address="0x" + "c" * 40,
        asset="ETH",
        amount=Decimal("1.0"),
        status=TxStatus.APPROVAL_PENDING,
        requires_approval=True,
        required_approvals=3,  # Need 3 to not auto-advance
        created_by=creator_id
    )
    db_session.add(tx)
    await db_session.flush()
    
    # Initialize services
    audit = AuditService(db_session)
    kyt = KYTService(db_session, audit)
    policy = PolicyService(db_session, audit)
    signing = SigningService(db_session, audit)
    ethereum = EthereumService(db_session, audit)
    orchestrator = TxOrchestrator(db_session, audit, kyt, policy, signing, ethereum)
    
    # First approval - should succeed
    await orchestrator.process_approval(
        tx.id,
        approver_id,
        "APPROVED",
        "First vote",
        f"test-{uuid4()}"
    )
    
    # Second approval by same user - should fail
    with pytest.raises(ValueError) as exc_info:
        await orchestrator.process_approval(
            tx.id,
            approver_id,
            "APPROVED",
            "Second vote attempt",
            f"test-{uuid4()}"
        )
    
    assert "already voted" in str(exc_info.value)

