"""add all missing columns safely

Revision ID: 20251210_add_all_missing_columns
Revises: 20251204134624_add_pdf_metadata_and_snippets
Create Date: 2025-12-10 01:00:00.000000

This migration adds ALL columns that might be missing from the database schema.
It safely checks for existence before adding each column.

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


# revision identifiers, used by Alembic.
revision = '20251210_add_all_missing_columns'
down_revision = '1bbe8f1675f2'  # FIXED: Should come AFTER add_analyst_notes_columns
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    """Add all missing columns safely."""
    
    # SCAN TABLE
    if not column_exists('scan', 'company'):
        op.add_column('scan', sa.Column('company', sa.String(256), nullable=True))
    
    if not column_exists('scan', 'is_sox_vendor'):
        op.add_column('scan', sa.Column('is_sox_vendor', sa.Boolean(), nullable=True))
        op.execute("UPDATE scan SET is_sox_vendor = FALSE WHERE is_sox_vendor IS NULL")
    
    if not column_exists('scan', 'report_type'):
        # Create ENUM type if it doesn't exist
        report_type_enum = ENUM('SOC1', 'SOC2', 'COMBINED', name='reporttype', create_type=False)
        report_type_enum.create(op.get_bind(), checkfirst=True)
        op.add_column('scan', sa.Column('report_type', report_type_enum, nullable=False, server_default='SOC2'))
    
    if not column_exists('scan', 'as_of_date'):
        op.add_column('scan', sa.Column('as_of_date', sa.DateTime(), nullable=True))
    
    if not column_exists('scan', 'progress_status'):
        op.add_column('scan', sa.Column('progress_status', sa.String(128), nullable=True))
    
    if not column_exists('scan', 'elapsed_seconds'):
        op.add_column('scan', sa.Column('elapsed_seconds', sa.Float(), nullable=True))
    
    if not column_exists('scan', 'toc_page_offset'):
        op.add_column('scan', sa.Column('toc_page_offset', sa.Integer(), nullable=True))
    
    if not column_exists('scan', 'detected_standards'):
        op.add_column('scan', sa.Column('detected_standards', sa.JSON(), nullable=True))
    
    if not column_exists('scan', 'active_frameworks'):
        op.add_column('scan', sa.Column('active_frameworks', sa.JSON(), nullable=True))
    
    # COMPANY TABLE
    if not column_exists('company', 'company_domain'):
        op.add_column('company', sa.Column('company_domain', sa.String(256), nullable=True))
        op.create_index('ix_company_company_domain', 'company', ['company_domain'], unique=False)
    
    if not column_exists('company', 'logo_url'):
        op.add_column('company', sa.Column('logo_url', sa.String(512), nullable=True))
    
    # CONTROL TABLE
    if not column_exists('control', 'has_deviation'):
        op.add_column('control', sa.Column('has_deviation', sa.Boolean(), nullable=True))
    
    if not column_exists('control', 'deviation_desc'):
        op.add_column('control', sa.Column('deviation_desc', sa.Text(), nullable=True))
    
    if not column_exists('control', 'control_page_refs'):
        op.add_column('control', sa.Column('control_page_refs', sa.JSON(), nullable=True))
    
    if not column_exists('control', 'financial_assertions'):
        op.add_column('control', sa.Column('financial_assertions', sa.JSON(), nullable=True))
    
    if not column_exists('control', 'framework_category'):
        op.add_column('control', sa.Column('framework_category', sa.String(32), nullable=True))
    
    if not column_exists('control', 'control_tsc_mappings'):
        op.add_column('control', sa.Column('control_tsc_mappings', sa.JSON(), nullable=True))
    
    if not column_exists('control', 'control_coso_mappings'):
        op.add_column('control', sa.Column('control_coso_mappings', sa.JSON(), nullable=True))
    
    if not column_exists('control', 'framework_mappings'):
        op.add_column('control', sa.Column('framework_mappings', sa.JSON(), nullable=True))
    
    if not column_exists('control', 'primary_framework'):
        op.add_column('control', sa.Column('primary_framework', sa.String(64), nullable=True))
    
    if not column_exists('control', 'primary_criterion_id'):
        op.add_column('control', sa.Column('primary_criterion_id', sa.String(128), nullable=True))
    
    if not column_exists('control', 'primary_confidence'):
        op.add_column('control', sa.Column('primary_confidence', sa.Float(), nullable=True))
    
    if not column_exists('control', 'analyst_notes'):
        op.add_column('control', sa.Column('analyst_notes', sa.Text(), nullable=True))
    
    if not column_exists('control', 'verification_status'):
        op.add_column('control', sa.Column('verification_status', sa.String(32), nullable=True))
    
    if not column_exists('control', 'verification_metadata'):
        op.add_column('control', sa.Column('verification_metadata', sa.JSON(), nullable=True))
    
    if not column_exists('control', 'pattern_confidence'):
        op.add_column('control', sa.Column('pattern_confidence', sa.Float(), nullable=True))
    
    if not column_exists('control', 'final_confidence'):
        op.add_column('control', sa.Column('final_confidence', sa.Float(), nullable=True))
    
    if not column_exists('control', 'deviation_summary'):
        op.add_column('control', sa.Column('deviation_summary', sa.Text(), nullable=True))
    
    if not column_exists('control', 'merge_history'):
        op.add_column('control', sa.Column('merge_history', sa.JSON(), nullable=True))
    
    if not column_exists('control', 'is_duplicate_instance'):
        op.add_column('control', sa.Column('is_duplicate_instance', sa.Boolean(), nullable=True, server_default='false'))
    
    if not column_exists('control', 'duplicate_group_id'):
        op.add_column('control', sa.Column('duplicate_group_id', sa.String(128), nullable=True))
    
    if not column_exists('control', 'instance_differentiator'):
        op.add_column('control', sa.Column('instance_differentiator', sa.JSON(), nullable=True))
    
    # CUEC TABLE
    if not column_exists('cuec', 'cuec_page_refs'):
        op.add_column('cuec', sa.Column('cuec_page_refs', sa.JSON(), nullable=True))
    
    if not column_exists('cuec', 'cuec_tsc_mappings'):
        op.add_column('cuec', sa.Column('cuec_tsc_mappings', sa.JSON(), nullable=True))
    
    if not column_exists('cuec', 'cuec_coso_mappings'):
        op.add_column('cuec', sa.Column('cuec_coso_mappings', sa.JSON(), nullable=True))
    
    if not column_exists('cuec', 'framework_mappings'):
        op.add_column('cuec', sa.Column('framework_mappings', sa.JSON(), nullable=True))
    
    if not column_exists('cuec', 'primary_framework'):
        op.add_column('cuec', sa.Column('primary_framework', sa.String(64), nullable=True))
    
    if not column_exists('cuec', 'primary_criterion_id'):
        op.add_column('cuec', sa.Column('primary_criterion_id', sa.String(128), nullable=True))
    
    if not column_exists('cuec', 'primary_confidence'):
        op.add_column('cuec', sa.Column('primary_confidence', sa.Float(), nullable=True))
    
    if not column_exists('cuec', 'analyst_notes'):
        op.add_column('cuec', sa.Column('analyst_notes', sa.Text(), nullable=True))
    
    # SUBSERVICE_ORG TABLE
    if not column_exists('subservice_org', 'analyst_notes'):
        op.add_column('subservice_org', sa.Column('analyst_notes', sa.Text(), nullable=True))


def downgrade():
    """Remove all added columns."""
    # This is intentionally simplified - in production you'd want to check existence before dropping
    pass  # Downgrade not implemented - too risky to auto-drop columns
