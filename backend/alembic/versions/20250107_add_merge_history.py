"""Add merge_history column to control table

Revision ID: 20250107_add_merge_history
Revises: 20251121_add_elapsed_seconds
Create Date: 2025-01-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250107_add_merge_history'
down_revision = '20251121_add_elapsed_seconds'
branch_labels = None
depends_on = None


def upgrade():
    # Add merge_history column to control table
    op.add_column('control', sa.Column('merge_history', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade():
    # Remove merge_history column from control table
    op.drop_column('control', 'merge_history')
