"""add_performance_indexes

Revision ID: 55d04962f87e
Revises: 20251210_add_all_missing_columns
Create Date: 2025-12-12 02:49:53.961499

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '55d04962f87e'
down_revision = '20251210_add_all_missing_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add performance indexes for frequently queried columns
    op.create_index('idx_control_scan_id', 'control', ['scan_id'])
    op.create_index('idx_control_merged_to', 'control', ['merged_to_control_id'])
    op.create_index('idx_control_confidence', 'control', ['control_confidence'])
    op.create_index('idx_cuec_scan_id', 'cuec', ['scan_id'])
    op.create_index('idx_suborg_scan_id', 'subserviceorg', ['scan_id'])
    op.create_index('idx_scan_status', 'scan', ['status'])
    op.create_index('idx_scan_report_type', 'scan', ['report_type'])
    # Composite index for common query pattern
    op.create_index('idx_control_scan_merged', 'control', ['scan_id', 'merged_to_control_id'])


def downgrade() -> None:
    # Drop indexes in reverse order for clean rollback
    op.drop_index('idx_control_scan_merged', 'control')
    op.drop_index('idx_scan_report_type', 'scan')
    op.drop_index('idx_scan_status', 'scan')
    op.drop_index('idx_suborg_scan_id', 'subserviceorg')
    op.drop_index('idx_cuec_scan_id', 'cuec')
    op.drop_index('idx_control_confidence', 'control')
    op.drop_index('idx_control_merged_to', 'control')
    op.drop_index('idx_control_scan_id', 'control')

