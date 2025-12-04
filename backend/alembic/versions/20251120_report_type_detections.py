"""Add report_type_detections table

Revision ID: 20251120_report_type_detections
Revises: 33a1ce8acc7a
Create Date: 2025-11-20 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251120_report_type_detections'
down_revision = '33a1ce8acc7a'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create report_type_detections table for caching GPT-based report type detection results.
    
    This table stores:
    - PDF hash for caching
    - Detected report type and subtype
    - Confidence score
    - Evidence used for detection
    - User override information
    - Cache metadata
    """
    op.create_table(
        'report_type_detections',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pdf_hash', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('detected_type', sa.String(32), nullable=False),  # 'SOC1', 'SOC2', 'COMBINED'
        sa.Column('detected_subtype', sa.String(32), nullable=False),  # 'TYPE1', 'TYPE2'
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=True),  # Array of key evidence strings
        sa.Column('analysis_stage', sa.String(16), nullable=False),  # 'quick' or 'deep'
        sa.Column('user_confirmed_type', sa.String(32), nullable=True),  # User override if any
        sa.Column('user_confirmed_subtype', sa.String(32), nullable=True),
        sa.Column('user_confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=True),  # For TTL-based cache expiry
    )
    
    # Create index on created_at for cleanup queries
    op.create_index(
        'ix_report_type_detections_created_at',
        'report_type_detections',
        ['created_at']
    )


def downgrade():
    """Remove report_type_detections table."""
    op.drop_index('ix_report_type_detections_created_at', table_name='report_type_detections')
    op.drop_table('report_type_detections')
