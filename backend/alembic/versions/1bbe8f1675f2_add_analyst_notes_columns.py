"""add_analyst_notes_columns

Revision ID: 1bbe8f1675f2
Revises: 724d6ce5c265
Create Date: 2025-12-09 18:49:58.253282

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1bbe8f1675f2'
down_revision = '724d6ce5c265'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add analyst_notes column to control table
    op.add_column('control', sa.Column('analyst_notes', sa.Text(), nullable=True))
    
    # Add analyst_notes column to cuec table
    op.add_column('cuec', sa.Column('analyst_notes', sa.Text(), nullable=True))
    
    # Add analyst_notes column to subservice_org table
    op.add_column('subservice_org', sa.Column('analyst_notes', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove analyst_notes column from subservice_org table
    op.drop_column('subservice_org', 'analyst_notes')
    
    # Remove analyst_notes column from cuec table
    op.drop_column('cuec', 'analyst_notes')
    
    # Remove analyst_notes column from control table
    op.drop_column('control', 'analyst_notes')

