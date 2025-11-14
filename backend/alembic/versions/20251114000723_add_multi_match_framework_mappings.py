"""add multi-match framework mappings

Revision ID: 20251114000723
Revises: a1b2c3d4e5f6
Create Date: 2025-11-14 00:07:23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251114000723'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    """Add JSON columns for multi-match TSC/COSO framework mappings."""
    # Add columns to control table
    op.add_column('control', sa.Column('control_tsc_mappings', sa.JSON(), nullable=True))
    op.add_column('control', sa.Column('control_coso_mappings', sa.JSON(), nullable=True))
    
    # Add columns to cuec table
    op.add_column('cuec', sa.Column('cuec_tsc_mappings', sa.JSON(), nullable=True))
    op.add_column('cuec', sa.Column('cuec_coso_mappings', sa.JSON(), nullable=True))
    
    # Set default empty arrays for existing rows
    op.execute("UPDATE control SET control_tsc_mappings = '[]'::json WHERE control_tsc_mappings IS NULL")
    op.execute("UPDATE control SET control_coso_mappings = '[]'::json WHERE control_coso_mappings IS NULL")
    op.execute("UPDATE cuec SET cuec_tsc_mappings = '[]'::json WHERE cuec_tsc_mappings IS NULL")
    op.execute("UPDATE cuec SET cuec_coso_mappings = '[]'::json WHERE cuec_coso_mappings IS NULL")


def downgrade():
    """Remove multi-match framework mapping columns."""
    op.drop_column('cuec', 'cuec_coso_mappings')
    op.drop_column('cuec', 'cuec_tsc_mappings')
    op.drop_column('control', 'control_coso_mappings')
    op.drop_column('control', 'control_tsc_mappings')
