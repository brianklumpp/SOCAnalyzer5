"""add_pdf_metadata_and_snippets

Revision ID: 20251204134624
Revises: 20250107_add_merge_history
Create Date: 2025-12-04 13:46:24

Add PDF metadata columns for split-view PDF viewer feature:
- scan.sections (JSONB): Stores section_results.json for fast API access
- control/cuec/subservice_org.pdf_snippet (TEXT): 150-200 char snippets for PDF text search
- Indexes: GIN indexes for performance on JSONB and text search
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251204134624'
down_revision = '20250107_add_merge_history'
branch_labels = None
depends_on = None


def upgrade():
    # Add sections JSONB column to scan table
    op.add_column('scan', sa.Column('sections', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Create GIN index on sections for fast JSONB queries
    op.create_index('idx_scan_sections', 'scan', ['sections'], unique=False, postgresql_using='gin')
    
    # Add pdf_snippet TEXT column to control table
    op.add_column('control', sa.Column('pdf_snippet', sa.Text(), nullable=True))
    
    # Create GIN index on control.pdf_snippet for full-text search
    op.execute("""
        CREATE INDEX idx_control_pdf_snippet ON control 
        USING GIN(to_tsvector('english', COALESCE(pdf_snippet, '')))
    """)
    
    # Add pdf_snippet TEXT column to cuec table
    op.add_column('cuec', sa.Column('pdf_snippet', sa.Text(), nullable=True))
    
    # Create GIN index on cuec.pdf_snippet for full-text search
    op.execute("""
        CREATE INDEX idx_cuec_pdf_snippet ON cuec 
        USING GIN(to_tsvector('english', COALESCE(pdf_snippet, '')))
    """)
    
    # Add pdf_snippet TEXT column to subservice_org table
    op.add_column('subservice_org', sa.Column('pdf_snippet', sa.Text(), nullable=True))
    
    # Create GIN index on subservice_org.pdf_snippet for full-text search
    op.execute("""
        CREATE INDEX idx_subservice_org_pdf_snippet ON subservice_org 
        USING GIN(to_tsvector('english', COALESCE(pdf_snippet, '')))
    """)


def downgrade():
    # Drop indexes first
    op.execute("DROP INDEX IF EXISTS idx_subservice_org_pdf_snippet")
    op.execute("DROP INDEX IF EXISTS idx_cuec_pdf_snippet")
    op.execute("DROP INDEX IF EXISTS idx_control_pdf_snippet")
    op.drop_index('idx_scan_sections', table_name='scan', postgresql_using='gin')
    
    # Drop columns
    op.drop_column('subservice_org', 'pdf_snippet')
    op.drop_column('cuec', 'pdf_snippet')
    op.drop_column('control', 'pdf_snippet')
    op.drop_column('scan', 'sections')
