"""add elapsed_seconds to scan table

Revision ID: 20251121_add_elapsed_seconds
Revises: 20251121_add_company_logos
Create Date: 2025-11-21 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251121_add_elapsed_seconds'
down_revision = '20251121_add_company_logos'
branch_labels = None
depends_on = None


def upgrade():
    """Add elapsed_seconds column to scan table for historical progress tracking."""
    op.add_column('scan', sa.Column('elapsed_seconds', sa.Float(), nullable=True))


def downgrade():
    """Remove elapsed_seconds column from scan table."""
    op.drop_column('scan', 'elapsed_seconds')
