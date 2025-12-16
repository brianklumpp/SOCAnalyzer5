"""add model_config table

Revision ID: 20251215_model_config
Revises: 20251213_remove_legacy
Create Date: 2025-12-15

Adds model_config table for runtime model assignment configuration.
Supports dual-layer persistence (Redis + database) for instant updates with restart resilience.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251215_model_config'
down_revision = '04131ed40cc0'
branch_labels = None
depends_on = None


def upgrade():
    # Create model_config table for runtime model assignments
    op.create_table(
        'model_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('extractor_name', sa.String(length=100), nullable=False),
        sa.Column('model_name', sa.String(length=50), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('changed_by', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('extractor_name', name='uq_model_config_extractor_name')
    )
    
    # Create index on extractor_name for faster lookups
    op.create_index('ix_model_config_extractor_name', 'model_config', ['extractor_name'])


def downgrade():
    # Drop model_config table and its indexes
    op.drop_index('ix_model_config_extractor_name', table_name='model_config')
    op.drop_table('model_config')
