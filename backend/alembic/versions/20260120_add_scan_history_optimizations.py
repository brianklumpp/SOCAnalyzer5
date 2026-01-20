"""add_scan_history_optimizations

Revision ID: 20260120_scan_opt
Revises: 20251219_add_audit_tracking
Create Date: 2026-01-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260120_scan_opt'
down_revision = '20251219_add_audit_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add performance optimizations for scan history:
    - Foreign key constraint on company.scan_id
    - Composite index for company lookups
    - Index on scan.scan_date for ordering
    """
    
    # Add foreign key constraint (with CASCADE delete)
    # This formalizes the relationship that already exists in the application
    op.create_foreign_key(
        'fk_company_scan_id',
        'company', 'scan',
        ['scan_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Add composite index for efficient company lookups by scan_id with confidence sorting
    # This speeds up queries that need to find the highest confidence company for a scan
    op.create_index(
        'idx_company_scan_confidence',
        'company',
        ['scan_id', 'confidence', 'id'],
        postgresql_using='btree'
    )
    
    # Add index on scan.scan_date for efficient ordering in history queries
    # Using DESC for descending order (most recent first)
    op.create_index(
        'idx_scan_date_desc',
        'scan',
        [sa.text('scan_date DESC')],
        postgresql_using='btree'
    )


def downgrade() -> None:
    """Remove performance optimizations"""
    op.drop_index('idx_scan_date_desc', 'scan')
    op.drop_index('idx_company_scan_confidence', 'company')
    op.drop_constraint('fk_company_scan_id', 'company', type_='foreignkey')
