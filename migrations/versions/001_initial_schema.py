"""Initial schema with all tables.

Revision ID: 001
Revises: 
Create Date: 2024-01-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('username', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('ADMIN', 'OPERATOR', 'COMPLIANCE', 'VIEWER', name='userrole'), default='VIEWER'),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Wallets table
    op.create_table(
        'wallets',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('address', sa.String(42), unique=True, nullable=False, index=True),
        sa.Column('wallet_type', sa.Enum('RETAIL', 'TREASURY', 'OPS', 'SETTLEMENT', name='wallettype'), nullable=False),
        sa.Column('subject_id', sa.String(255), nullable=False, index=True),
        sa.Column('tags', postgresql.JSON(), nullable=True),
        sa.Column('risk_profile', sa.Enum('LOW', 'MEDIUM', 'HIGH', name='riskprofile'), default='MEDIUM'),
        sa.Column('key_ref', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('idempotency_key', sa.String(255), unique=True, nullable=True),
    )
    op.create_index('ix_wallets_subject_type', 'wallets', ['subject_id', 'wallet_type'])

    # Wallet roles table
    op.create_table(
        'wallet_roles',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('wallets.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('role', sa.Enum('OWNER', 'OPERATOR', 'VIEWER', 'APPROVER', name='walletroletype'), nullable=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('created_by', postgresql.UUID(as_uuid=False), nullable=False),
    )
    op.create_index('ix_wallet_roles_wallet_user', 'wallet_roles', ['wallet_id', 'user_id'], unique=True)

    # KYT Cases table
    op.create_table(
        'kyt_cases',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('address', sa.String(42), nullable=False, index=True),
        sa.Column('direction', sa.String(20), nullable=False),
        sa.Column('reason', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), default='PENDING'),
        sa.Column('resolved_by', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolution_comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )

    # Transaction requests table
    op.create_table(
        'tx_requests',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('wallets.id'), nullable=False, index=True),
        sa.Column('tx_type', sa.Enum('WITHDRAW', 'TRANSFER', 'CONTRACT_CALL', name='txtype'), nullable=False),
        sa.Column('to_address', sa.String(42), nullable=False, index=True),
        sa.Column('asset', sa.String(50), nullable=False, default='ETH'),
        sa.Column('amount', sa.Numeric(36, 18), nullable=False),
        sa.Column('data', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum(
            'SUBMITTED', 'KYT_PENDING', 'KYT_BLOCKED', 'KYT_REVIEW',
            'POLICY_EVAL_PENDING', 'POLICY_BLOCKED', 'APPROVAL_PENDING',
            'REJECTED', 'SIGN_PENDING', 'SIGNED', 'FAILED_SIGN',
            'BROADCAST_PENDING', 'BROADCASTED', 'FAILED_BROADCAST',
            'CONFIRMING', 'CONFIRMED', 'FINALIZED',
            name='txstatus'
        ), default='SUBMITTED', index=True),
        sa.Column('kyt_result', sa.String(50), nullable=True),
        sa.Column('kyt_case_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('kyt_cases.id'), nullable=True),
        sa.Column('policy_result', postgresql.JSON(), nullable=True),
        sa.Column('requires_approval', sa.Boolean(), default=False),
        sa.Column('required_approvals', sa.Integer(), default=0),
        sa.Column('signed_tx', sa.Text(), nullable=True),
        sa.Column('tx_hash', sa.String(66), nullable=True, index=True),
        sa.Column('gas_price', sa.Numeric(36, 0), nullable=True),
        sa.Column('gas_limit', sa.Integer(), nullable=True),
        sa.Column('nonce', sa.Integer(), nullable=True),
        sa.Column('block_number', sa.Integer(), nullable=True),
        sa.Column('confirmations', sa.Integer(), default=0),
        sa.Column('created_by', postgresql.UUID(as_uuid=False), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('idempotency_key', sa.String(255), unique=True, nullable=True),
    )
    op.create_index('ix_tx_requests_status_created', 'tx_requests', ['status', 'created_at'])
    op.create_index('ix_tx_requests_wallet_status', 'tx_requests', ['wallet_id', 'status'])

    # Approvals table
    op.create_table(
        'approvals',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('tx_request_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('tx_requests.id'), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('decision', sa.String(20), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )
    op.create_index('ix_approvals_tx_user', 'approvals', ['tx_request_id', 'user_id'], unique=True)

    # Policies table
    op.create_table(
        'policies',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('policy_type', sa.Enum(
            'ADDRESS_DENYLIST', 'TOKEN_DENYLIST', 'TX_LIMIT', 'DAILY_LIMIT', 'APPROVAL_REQUIRED',
            name='policytype'
        ), nullable=False, index=True),
        sa.Column('address', sa.String(42), nullable=True, index=True),
        sa.Column('token', sa.String(42), nullable=True),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('wallets.id'), nullable=True, index=True),
        sa.Column('wallet_type', sa.String(50), nullable=True, index=True),
        sa.Column('limit_amount', sa.Numeric(36, 18), nullable=True),
        sa.Column('required_approvals', sa.Integer(), default=0),
        sa.Column('config', postgresql.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('created_by', postgresql.UUID(as_uuid=False), nullable=False),
    )

    # Daily volumes table
    op.create_table(
        'daily_volumes',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('wallets.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('asset', sa.String(50), nullable=False, default='ETH'),
        sa.Column('total_amount', sa.Numeric(36, 18), default=0),
        sa.Column('tx_count', sa.Integer(), default=0),
    )
    op.create_index('ix_daily_volumes_wallet_date_asset', 'daily_volumes', ['wallet_id', 'date', 'asset'], unique=True)

    # Audit events table
    op.create_table(
        'audit_events',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('sequence_number', sa.Integer(), autoincrement=True, unique=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(), default=sa.func.now(), nullable=False, index=True),
        sa.Column('event_type', sa.Enum(
            'WALLET_CREATED', 'WALLET_ROLE_ASSIGNED', 'WALLET_ROLE_REVOKED',
            'TX_REQUEST_CREATED', 'TX_STATUS_CHANGED', 'TX_KYT_EVALUATED',
            'TX_POLICY_EVALUATED', 'TX_APPROVAL_RECEIVED', 'TX_REJECTION_RECEIVED',
            'TX_SIGNED', 'TX_BROADCASTED', 'TX_CONFIRMED', 'TX_FINALIZED', 'TX_FAILED',
            'KYT_CASE_CREATED', 'KYT_CASE_RESOLVED',
            'DEPOSIT_DETECTED', 'DEPOSIT_KYT_EVALUATED',
            'POLICY_CREATED', 'POLICY_UPDATED', 'POLICY_DELETED',
            'USER_LOGIN', 'USER_LOGOUT',
            name='auditeventtype'
        ), nullable=False, index=True),
        sa.Column('actor_id', postgresql.UUID(as_uuid=False), nullable=True, index=True),
        sa.Column('actor_type', sa.String(50), default='USER'),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=False), nullable=True, index=True),
        sa.Column('entity_refs', postgresql.JSONB(), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=True),
        sa.Column('correlation_id', sa.String(255), nullable=False, index=True),
        sa.Column('prev_hash', sa.String(64), nullable=True),
        sa.Column('hash', sa.String(64), nullable=False, index=True),
    )
    op.create_index('ix_audit_events_entity', 'audit_events', ['entity_type', 'entity_id'])
    op.create_index('ix_audit_events_timestamp_type', 'audit_events', ['timestamp', 'event_type'])

    # Deposits table
    op.create_table(
        'deposits',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=False), nullable=False, index=True),
        sa.Column('tx_hash', sa.String(66), nullable=False, unique=True, index=True),
        sa.Column('from_address', sa.String(42), nullable=False, index=True),
        sa.Column('asset', sa.String(50), nullable=False, default='ETH'),
        sa.Column('amount', sa.String(78), nullable=False),
        sa.Column('block_number', sa.Integer(), nullable=False),
        sa.Column('kyt_result', sa.String(50), nullable=True),
        sa.Column('kyt_case_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('detected_at', sa.DateTime(), default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('deposits')
    op.drop_table('audit_events')
    op.drop_table('daily_volumes')
    op.drop_table('policies')
    op.drop_table('approvals')
    op.drop_table('tx_requests')
    op.drop_table('kyt_cases')
    op.drop_table('wallet_roles')
    op.drop_table('wallets')
    op.drop_table('users')
    
    # Drop enums
    op.execute("DROP TYPE IF EXISTS auditeventtype")
    op.execute("DROP TYPE IF EXISTS policytype")
    op.execute("DROP TYPE IF EXISTS txstatus")
    op.execute("DROP TYPE IF EXISTS txtype")
    op.execute("DROP TYPE IF EXISTS walletroletype")
    op.execute("DROP TYPE IF EXISTS riskprofile")
    op.execute("DROP TYPE IF EXISTS wallettype")
    op.execute("DROP TYPE IF EXISTS userrole")

