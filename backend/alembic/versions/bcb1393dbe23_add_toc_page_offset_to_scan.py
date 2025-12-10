"""add_toc_page_offset_to_scan

Revision ID: bcb1393dbe23
Revises: 20251204134624
Create Date: 2025-12-05 10:57:49.199821

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'bcb1393dbe23'
down_revision = '20251204134624'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add toc_page_offset column to scan table
    op.add_column('scan', sa.Column('toc_page_offset', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Remove toc_page_offset column from scan table
    op.drop_column('scan', 'toc_page_offset')

