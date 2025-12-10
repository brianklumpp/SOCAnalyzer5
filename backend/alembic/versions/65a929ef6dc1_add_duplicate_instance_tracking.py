"""add_duplicate_instance_tracking

Revision ID: 65a929ef6dc1
Revises: 09d1ae6a4827
Create Date: 2025-12-05 11:53:27.648153

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '65a929ef6dc1'
down_revision = '09d1ae6a4827'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add duplicate instance tracking fields to control table
    op.add_column('control', sa.Column('is_duplicate_instance', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('control', sa.Column('duplicate_group_id', sa.String(128), nullable=True))
    op.add_column('control', sa.Column('instance_differentiator', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove duplicate instance tracking fields from control table
    op.drop_column('control', 'instance_differentiator')
    op.drop_column('control', 'duplicate_group_id')
    op.drop_column('control', 'is_duplicate_instance')

