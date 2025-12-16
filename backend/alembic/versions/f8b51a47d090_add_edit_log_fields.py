"""add_edit_log_fields

Revision ID: f8b51a47d090
Revises: 55d04962f87e
Create Date: 2025-12-13 19:35:57.913262

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f8b51a47d090'
down_revision = '55d04962f87e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add edit_log TEXT column to control table
    op.add_column('control', sa.Column('edit_log', sa.Text(), nullable=True))
    
    # Add edit_log TEXT column to cuec table
    op.add_column('cuec', sa.Column('edit_log', sa.Text(), nullable=True))
    
    # Add edit_log TEXT column to subservice_org table
    op.add_column('subservice_org', sa.Column('edit_log', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove edit_log column from all three tables
    op.drop_column('control', 'edit_log')
    op.drop_column('cuec', 'edit_log')
    op.drop_column('subservice_org', 'edit_log')

