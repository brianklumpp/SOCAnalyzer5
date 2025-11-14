"""add is_sox_vendor to scan

Revision ID: 20250207000001
Revises: 4f3812f8cda4
Create Date: 2025-02-07 00:00:01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250207000001'
down_revision = '4f3812f8cda4'
branch_labels = None
depends_on = None


def upgrade():
    """Add is_sox_vendor boolean column to scan table."""
    op.add_column('scan', sa.Column('is_sox_vendor', sa.Boolean(), nullable=True))
    
    # Set default False for existing rows
    op.execute("UPDATE scan SET is_sox_vendor = FALSE WHERE is_sox_vendor IS NULL")
    
    # Make column non-nullable with default
    op.alter_column('scan', 'is_sox_vendor', nullable=False, server_default=sa.false())


def downgrade():
    """Remove is_sox_vendor column from scan table."""
    op.drop_column('scan', 'is_sox_vendor')
