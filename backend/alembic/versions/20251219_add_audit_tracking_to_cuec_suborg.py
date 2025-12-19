"""add audit tracking to cuec and subservice_org tables

Revision ID: 20251219_add_audit_tracking
Revises: 3969d2dda78b
Create Date: 2025-12-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251219_add_audit_tracking'
down_revision = '3969d2dda78b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add audit tracking to CUEC table
    op.add_column('cuec', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('cuec', sa.Column('updated_by_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_cuec_updated_by', 'cuec', 'users', ['updated_by_user_id'], ['id'])
    
    # Add audit tracking to SubserviceOrg table
    op.add_column('subservice_org', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('subservice_org', sa.Column('updated_by_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_suborg_updated_by', 'subservice_org', 'users', ['updated_by_user_id'], ['id'])


def downgrade() -> None:
    # Remove audit tracking from SubserviceOrg
    op.drop_constraint('fk_suborg_updated_by', 'subservice_org', type_='foreignkey')
    op.drop_column('subservice_org', 'updated_by_user_id')
    op.drop_column('subservice_org', 'updated_at')
    
    # Remove audit tracking from CUEC
    op.drop_constraint('fk_cuec_updated_by', 'cuec', type_='foreignkey')
    op.drop_column('cuec', 'updated_by_user_id')
    op.drop_column('cuec', 'updated_at')
