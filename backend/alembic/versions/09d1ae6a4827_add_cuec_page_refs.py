"""add_cuec_page_refs

Revision ID: 09d1ae6a4827
Revises: bcb1393dbe23
Create Date: 2025-12-05 11:21:33.739433

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '09d1ae6a4827'
down_revision = 'bcb1393dbe23'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add cuec_page_refs column to cuec table
    op.add_column('cuec', sa.Column('cuec_page_refs', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove cuec_page_refs column from cuec table
    op.drop_column('cuec', 'cuec_page_refs')

