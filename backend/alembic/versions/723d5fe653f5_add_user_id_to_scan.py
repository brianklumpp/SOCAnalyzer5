"""add_user_id_to_scan

Revision ID: 723d5fe653f5
Revises: 7db38ce025c3
Create Date: 2026-02-15 00:20:15.209106

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '723d5fe653f5'
down_revision = '7db38ce025c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add user_id column to scan table
    op.add_column('scan', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_scan_user_id', 'scan', 'users', ['user_id'], ['id'])


def downgrade() -> None:
    # Remove user_id column from scan table
    op.drop_constraint('fk_scan_user_id', 'scan', type_='foreignkey')
    op.drop_column('scan', 'user_id')

