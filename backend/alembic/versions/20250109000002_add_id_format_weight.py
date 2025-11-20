"""add_id_format_weight

Revision ID: 20250109000002
Revises: 20250109000001
Create Date: 2025-01-09 00:00:02.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250109000002'
down_revision = '20250109000001'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add id_format_weight column to confidence_weights table.
    
    This is the 6th factor in the confidence scoring system, used to detect
    TSC reference heading anomalies by analyzing control ID format consistency.
    
    Default weight: 0.10 (10% of total)
    Other weights adjusted proportionally to maintain 90% total:
    - gpt_weight: 0.225 (22.5%)
    - pattern_weight: 0.18 (18%)
    - structure_weight: 0.18 (18%)
    - framework_weight: 0.18 (18%)
    - deviation_weight: 0.135 (13.5%)
    """
    op.add_column('confidence_weights', 
        sa.Column('id_format_weight', sa.Float(), nullable=True, server_default='0.10'))


def downgrade():
    """
    Remove id_format_weight column from confidence_weights table.
    """
    op.drop_column('confidence_weights', 'id_format_weight')
