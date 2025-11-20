"""add_control_id_pattern_analysis

Revision ID: 20250109000001
Revises: 20251117000001
Create Date: 2025-01-09 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250109000001'
down_revision = '20251117000001'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add control_id_pattern_analysis column to scan table.
    
    This column stores the results of control ID pattern analysis used for
    detecting TSC reference heading anomalies in the 6-factor confidence system.
    
    Format:
    {
        "CC6.": {
            "pattern_score": 0.2,
            "is_tsc_anomaly": true,
            "consensus_pattern": "LL#.#",
            "detected_pattern": "LL#."
        },
        ...
    }
    """
    op.add_column('scan', 
        sa.Column('control_id_pattern_analysis', postgresql.JSON(), nullable=True))


def downgrade():
    """
    Remove control_id_pattern_analysis column from scan table.
    """
    op.drop_column('scan', 'control_id_pattern_analysis')
