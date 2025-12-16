"""add_user_authentication

Revision ID: 94ab857cec4b
Revises: 20251215_model_config
Create Date: 2025-12-15 23:04:56.552714

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '94ab857cec4b'
down_revision = '20251215_model_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=128), nullable=False),
        sa.Column('email', sa.String(length=256), nullable=False),
        sa.Column('hashed_password', sa.String(length=256), nullable=False),
        sa.Column('full_name', sa.String(length=256), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    
    # Create refresh_tokens table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=256), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refresh_tokens_id'), 'refresh_tokens', ['id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True)
    
    # Add user_id column to scan table
    op.add_column('scan', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_scan_user_id'), 'scan', ['user_id'], unique=False)
    op.create_foreign_key('fk_scan_user', 'scan', 'users', ['user_id'], ['id'])
    
    # Update confidence_weight_audit to use user_id FK instead of nullable integer
    # First, add the new column
    op.add_column('confidence_weight_audit', sa.Column('changed_by_user_id_new', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_confidence_weight_audit_user', 'confidence_weight_audit', 'users', ['changed_by_user_id_new'], ['id'])
    # Note: Migration of data from changed_by_user_id to changed_by_user_id_new will be handled separately
    
    # Add user_id to control_review table
    op.add_column('control_review', sa.Column('reviewed_by_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_control_review_user', 'control_review', 'users', ['reviewed_by_user_id'], ['id'])
    
    # Add user_id to baselines table
    op.add_column('baselines', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_baselines_user', 'baselines', 'users', ['user_id'], ['id'])
    
    # Add user_id columns to pattern_review_queue table
    op.add_column('pattern_review_queue', sa.Column('approved_by_user_id', sa.Integer(), nullable=True))
    op.add_column('pattern_review_queue', sa.Column('rejected_by_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_pattern_review_approved_by', 'pattern_review_queue', 'users', ['approved_by_user_id'], ['id'])
    op.create_foreign_key('fk_pattern_review_rejected_by', 'pattern_review_queue', 'users', ['rejected_by_user_id'], ['id'])
    
    # Add updated_at and updated_by_user_id to control table for optimistic locking
    op.add_column('control', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('control', sa.Column('updated_by_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_control_updated_by', 'control', 'users', ['updated_by_user_id'], ['id'])


def downgrade() -> None:
    # Remove foreign keys and columns in reverse order
    op.drop_constraint('fk_control_updated_by', 'control', type_='foreignkey')
    op.drop_column('control', 'updated_by_user_id')
    op.drop_column('control', 'updated_at')
    
    op.drop_constraint('fk_pattern_review_rejected_by', 'pattern_review_queue', type_='foreignkey')
    op.drop_constraint('fk_pattern_review_approved_by', 'pattern_review_queue', type_='foreignkey')
    op.drop_column('pattern_review_queue', 'rejected_by_user_id')
    op.drop_column('pattern_review_queue', 'approved_by_user_id')
    
    op.drop_constraint('fk_baselines_user', 'baselines', type_='foreignkey')
    op.drop_column('baselines', 'user_id')
    
    op.drop_constraint('fk_control_review_user', 'control_review', type_='foreignkey')
    op.drop_column('control_review', 'reviewed_by_user_id')
    
    op.drop_constraint('fk_confidence_weight_audit_user', 'confidence_weight_audit', type_='foreignkey')
    op.drop_column('confidence_weight_audit', 'changed_by_user_id_new')
    
    op.drop_constraint('fk_scan_user', 'scan', type_='foreignkey')
    op.drop_index(op.f('ix_scan_user_id'), table_name='scan')
    op.drop_column('scan', 'user_id')
    
    op.drop_index(op.f('ix_refresh_tokens_token_hash'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')

