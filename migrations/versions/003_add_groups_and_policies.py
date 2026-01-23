"""Add groups, policy sets, and address books for tiered policies

Revision ID: 003_add_groups_and_policies
Revises: 002_add_mpc_tables
Create Date: 2026-01-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new audit event types to existing enum
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'GROUP_CREATED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'GROUP_UPDATED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'GROUP_DELETED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'GROUP_MEMBER_ADDED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'GROUP_MEMBER_REMOVED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'USER_GROUP_ENROLLED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'ADDRESS_BOOK_ENTRY_ADDED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'ADDRESS_BOOK_ENTRY_REMOVED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'POLICY_SET_CREATED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'POLICY_SET_UPDATED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'POLICY_SET_ASSIGNED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'POLICY_RULE_ADDED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'POLICY_RULE_UPDATED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'POLICY_RULE_REMOVED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'KYT_SKIPPED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE IF NOT EXISTS 'APPROVALS_SKIPPED'")

    # Add new TxStatus enum values for conditional flow
    op.execute("ALTER TYPE txstatus ADD VALUE IF NOT EXISTS 'KYT_SKIPPED'")
    op.execute("ALTER TYPE txstatus ADD VALUE IF NOT EXISTS 'APPROVAL_SKIPPED'")

    # Create new enums
    from sqlalchemy.dialects.postgresql import ENUM as pgENUM

    addresskind = pgENUM('ALLOW', 'DENY', name='addresskind', create_type=False)
    policydecision = pgENUM('ALLOW', 'BLOCK', 'CONTINUE', name='policydecision', create_type=False)

    addresskind.create(op.get_bind(), checkfirst=True)
    policydecision.create(op.get_bind(), checkfirst=True)

    # Create groups table
    op.create_table('groups',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_by', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_groups_is_default', 'groups', ['is_default'])

    # Create group_members table
    op.create_table('group_members',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'user_id', name='uq_group_member')
    )
    op.create_index('ix_group_members_group_id', 'group_members', ['group_id'])
    op.create_index('ix_group_members_user_id', 'group_members', ['user_id'])

    # Create group_address_book table
    op.create_table('group_address_book',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('address', sa.String(42), nullable=False),
        sa.Column('kind', addresskind, nullable=False),
        sa.Column('label', sa.String(255), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'address', name='uq_group_address')
    )
    op.create_index('ix_group_address_book_group_id', 'group_address_book', ['group_id'])
    op.create_index('ix_group_address_book_address', 'group_address_book', ['address'])
    op.create_index('ix_group_address_book_kind', 'group_address_book', ['kind'])

    # Create policy_sets table
    op.create_table('policy_sets',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('snapshot_hash', sa.String(64), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'version', name='uq_policy_set_name_version')
    )
    op.create_index('ix_policy_sets_name', 'policy_sets', ['name'])
    op.create_index('ix_policy_sets_is_active', 'policy_sets', ['is_active'])

    # Create policy_rules table
    op.create_table('policy_rules',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('policy_set_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('rule_id', sa.String(50), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('conditions', postgresql.JSONB(), nullable=False),
        sa.Column('decision', policydecision, nullable=False),
        sa.Column('kyt_required', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('approval_required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('approval_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['policy_set_id'], ['policy_sets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('policy_set_id', 'rule_id', name='uq_policy_rule')
    )
    op.create_index('ix_policy_rules_policy_set_id', 'policy_rules', ['policy_set_id'])
    op.create_index('ix_policy_rules_priority', 'policy_rules', ['priority'])

    # Create group_policies table (assignment)
    op.create_table('group_policies',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('policy_set_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('assigned_by', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['policy_set_id'], ['policy_sets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', name='uq_group_policy')
    )
    op.create_index('ix_group_policies_group_id', 'group_policies', ['group_id'])
    op.create_index('ix_group_policies_policy_set_id', 'group_policies', ['policy_set_id'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('group_policies')
    op.drop_table('policy_rules')
    op.drop_table('policy_sets')
    op.drop_table('group_address_book')
    op.drop_table('group_members')
    op.drop_table('groups')

    # Drop enums
    op.execute("DROP TYPE IF EXISTS policydecision")
    op.execute("DROP TYPE IF EXISTS addresskind")

    # Note: Cannot easily remove enum values in PostgreSQL
    # The audit event types will remain but be unused
