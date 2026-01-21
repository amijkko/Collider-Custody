"""Add MPC tables for tECDSA signing

Revision ID: 002_add_mpc_tables
Revises: 001_initial_schema
Create Date: 2026-01-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new MPC audit event types to existing enum
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'MPC_KEYGEN_STARTED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'MPC_KEYGEN_COMPLETED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'MPC_KEYGEN_FAILED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'MPC_SIGN_STARTED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'MPC_SIGN_COMPLETED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'MPC_SIGN_FAILED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'SIGN_PERMIT_ISSUED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'SIGN_PERMIT_REJECTED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'MPC_NODE_QUARANTINED'")
    
    # Create enums explicitly first (types need to exist before columns that use them)
    from sqlalchemy.dialects.postgresql import ENUM as pgENUM
    
    custodybackend = pgENUM('DEV_SIGNER', 'MPC_TECDSA', name='custodybackend', create_type=False)
    walletstatus = pgENUM('PENDING_KEYGEN', 'ACTIVE', 'SUSPENDED', 'ARCHIVED', name='walletstatus', create_type=False)
    mpckeyset_status = pgENUM('PENDING', 'DKG_IN_PROGRESS', 'ACTIVE', 'ROTATING', 'COMPROMISED', 'ARCHIVED', name='mpckeyset_status', create_type=False)
    mpcsession_type = pgENUM('DKG', 'SIGNING', 'REFRESH', 'BACKUP', name='mpcsession_type', create_type=False)
    mpcsession_status = pgENUM('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'TIMEOUT', name='mpcsession_status', create_type=False)
    mpcnode_status = pgENUM('ACTIVE', 'INACTIVE', 'QUARANTINED', 'MAINTENANCE', name='mpcnode_status', create_type=False)
    mpcerror_category = pgENUM('TRANSIENT', 'PERMANENT', 'PROTOCOL_VIOLATION', name='mpcerror_category', create_type=False)
    
    # Create the enum types
    custodybackend.create(op.get_bind(), checkfirst=True)
    walletstatus.create(op.get_bind(), checkfirst=True)
    mpckeyset_status.create(op.get_bind(), checkfirst=True)
    mpcsession_type.create(op.get_bind(), checkfirst=True)
    mpcsession_status.create(op.get_bind(), checkfirst=True)
    mpcnode_status.create(op.get_bind(), checkfirst=True)
    mpcerror_category.create(op.get_bind(), checkfirst=True)
    
    # Add new columns to wallets table
    op.add_column('wallets', sa.Column('custody_backend', custodybackend, nullable=True))
    op.add_column('wallets', sa.Column('status', walletstatus, nullable=True))
    op.add_column('wallets', sa.Column('mpc_keyset_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column('wallets', sa.Column('mpc_threshold_t', sa.Integer(), nullable=True))
    op.add_column('wallets', sa.Column('mpc_total_n', sa.Integer(), nullable=True))
    
    # Set default values for existing wallets
    op.execute("UPDATE wallets SET custody_backend = 'DEV_SIGNER' WHERE custody_backend IS NULL")
    op.execute("UPDATE wallets SET status = 'ACTIVE' WHERE status IS NULL")
    
    # Make columns non-nullable
    op.alter_column('wallets', 'custody_backend', nullable=False, server_default='DEV_SIGNER')
    op.alter_column('wallets', 'status', nullable=False, server_default='ACTIVE')
    
    # Make address nullable for PENDING_KEYGEN wallets
    op.alter_column('wallets', 'address', nullable=True)
    op.alter_column('wallets', 'key_ref', type_=sa.String(512), nullable=True)
    
    # Create indexes for wallets
    op.create_index('ix_wallets_custody_backend', 'wallets', ['custody_backend'])
    op.create_index('ix_wallets_status', 'wallets', ['status'])
    op.create_index('ix_wallets_custody_status', 'wallets', ['custody_backend', 'status'])
    
    # Create MPC Keysets table
    op.create_table('mpc_keysets',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('threshold_t', sa.Integer(), nullable=False),
        sa.Column('total_n', sa.Integer(), nullable=False),
        sa.Column('public_key', sa.String(130), nullable=False),
        sa.Column('public_key_compressed', sa.String(66), nullable=False),
        sa.Column('address', sa.String(42), nullable=False),
        sa.Column('status', mpckeyset_status, nullable=True),
        sa.Column('cluster_id', sa.String(255), nullable=False, server_default='default'),
        sa.Column('key_ref', sa.String(512), nullable=False),
        sa.Column('participant_nodes', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('wallet_id')
    )
    op.create_index('ix_mpc_keysets_wallet_id', 'mpc_keysets', ['wallet_id'])
    op.create_index('ix_mpc_keysets_address', 'mpc_keysets', ['address'])
    op.create_index('ix_mpc_keysets_status', 'mpc_keysets', ['status'])
    
    # Create MPC Sessions table
    op.create_table('mpc_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('session_type', mpcsession_type, nullable=False),
        sa.Column('keyset_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('tx_request_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('tx_hash', sa.String(66), nullable=True),
        sa.Column('signature_r', sa.String(66), nullable=True),
        sa.Column('signature_s', sa.String(66), nullable=True),
        sa.Column('signature_v', sa.Integer(), nullable=True),
        sa.Column('permit_hash', sa.String(64), nullable=True),
        sa.Column('status', mpcsession_status, nullable=True),
        sa.Column('participant_nodes', postgresql.JSONB(), nullable=True),
        sa.Column('quorum_reached', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('error_category', mpcerror_category, nullable=True),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(255), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('timeout_at', sa.DateTime(), nullable=True),
        sa.Column('current_round', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('total_rounds', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['keyset_id'], ['mpc_keysets.id'], ),
        sa.ForeignKeyConstraint(['tx_request_id'], ['tx_requests.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_mpc_sessions_keyset_id', 'mpc_sessions', ['keyset_id'])
    op.create_index('ix_mpc_sessions_tx_request_id', 'mpc_sessions', ['tx_request_id'])
    op.create_index('ix_mpc_sessions_status', 'mpc_sessions', ['status'])
    op.create_index('ix_mpc_sessions_type_status', 'mpc_sessions', ['session_type', 'status'])
    
    # Create MPC Nodes table
    op.create_table('mpc_nodes',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('node_name', sa.String(255), nullable=False),
        sa.Column('cluster_id', sa.String(255), nullable=False, server_default='default'),
        sa.Column('endpoint_url', sa.String(512), nullable=False),
        sa.Column('zone', sa.String(100), nullable=False, server_default='default'),
        sa.Column('status', mpcnode_status, nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.Column('last_health_check', sa.DateTime(), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('quarantine_reason', sa.Text(), nullable=True),
        sa.Column('quarantined_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.String(50), nullable=True),
        sa.Column('capabilities', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('node_name')
    )
    op.create_index('ix_mpc_nodes_cluster_id', 'mpc_nodes', ['cluster_id'])
    op.create_index('ix_mpc_nodes_status', 'mpc_nodes', ['status'])
    
    # Create Signing Permits table
    op.create_table('signing_permits',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('tx_request_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('keyset_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('tx_hash', sa.String(66), nullable=False),
        sa.Column('kyt_result', sa.String(50), nullable=False),
        sa.Column('kyt_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('policy_result', sa.String(50), nullable=False),
        sa.Column('policy_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('approval_snapshot', postgresql.JSONB(), nullable=False),
        sa.Column('audit_anchor_hash', sa.String(64), nullable=False),
        sa.Column('permit_hash', sa.String(64), nullable=False),
        sa.Column('signature', sa.Text(), nullable=False),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('is_used', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('is_revoked', sa.Boolean(), nullable=True, server_default='false'),
        sa.ForeignKeyConstraint(['keyset_id'], ['mpc_keysets.id'], ),
        sa.ForeignKeyConstraint(['tx_request_id'], ['tx_requests.id'], ),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('permit_hash')
    )
    op.create_index('ix_signing_permits_tx_request', 'signing_permits', ['tx_request_id'])
    op.create_index('ix_signing_permits_expires', 'signing_permits', ['expires_at'])


def downgrade() -> None:
    # Drop tables
    op.drop_table('signing_permits')
    op.drop_table('mpc_nodes')
    op.drop_table('mpc_sessions')
    op.drop_table('mpc_keysets')
    
    # Drop indexes from wallets
    op.drop_index('ix_wallets_custody_status', 'wallets')
    op.drop_index('ix_wallets_status', 'wallets')
    op.drop_index('ix_wallets_custody_backend', 'wallets')
    
    # Drop columns from wallets
    op.drop_column('wallets', 'mpc_total_n')
    op.drop_column('wallets', 'mpc_threshold_t')
    op.drop_column('wallets', 'mpc_keyset_id')
    op.drop_column('wallets', 'status')
    op.drop_column('wallets', 'custody_backend')
    
    # Restore wallets columns
    op.alter_column('wallets', 'address', nullable=False)
    op.alter_column('wallets', 'key_ref', type_=sa.String(255), nullable=False)
    
    # Drop enums
    op.execute("DROP TYPE IF EXISTS mpcerror_category")
    op.execute("DROP TYPE IF EXISTS mpcnode_status")
    op.execute("DROP TYPE IF EXISTS mpcsession_status")
    op.execute("DROP TYPE IF EXISTS mpcsession_type")
    op.execute("DROP TYPE IF EXISTS mpckeyset_status")
    op.execute("DROP TYPE IF EXISTS walletstatus")
    op.execute("DROP TYPE IF EXISTS custodybackend")

