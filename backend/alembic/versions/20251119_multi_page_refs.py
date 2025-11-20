"""Add multi-page references support

Revision ID: 20251119_multi_page_refs
Revises: 20251114000723_add_multi_match_framework_mappings
Create Date: 2025-11-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251119_multi_page_refs'
down_revision = '20250109000002'
branch_labels = None
depends_on = None


def upgrade():
    """
    Migrate from single page reference to multi-page array storage.
    
    Changes:
    1. Add control_page_refs JSON column to store array of page numbers
    2. Migrate existing control_page_ref integer data to array format
    3. Drop old control_page_ref integer column
    """
    # Add new JSON column for page references array
    op.add_column('control', sa.Column('control_page_refs', sa.JSON(), nullable=True))
    
    # Migrate existing data: convert single integer to array
    op.execute("""
        UPDATE control 
        SET control_page_refs = CASE 
            WHEN control_page_ref IS NOT NULL 
            THEN json_build_array(control_page_ref) 
            ELSE '[]'::json 
        END
    """)
    
    # Drop old single-page column
    op.drop_column('control', 'control_page_ref')


def downgrade():
    """
    Rollback to single page reference.
    
    WARNING: This will lose multi-page data! Only first page will be preserved.
    """
    # Add back the old integer column
    op.add_column('control', sa.Column('control_page_ref', sa.Integer(), nullable=True))
    
    # Migrate back: take first element from array
    op.execute("""
        UPDATE control 
        SET control_page_ref = CASE 
            WHEN control_page_refs IS NOT NULL 
                AND jsonb_array_length(control_page_refs::jsonb) > 0
            THEN (control_page_refs::jsonb->0)::text::integer
            ELSE NULL 
        END
    """)
    
    # Drop the JSON array column
    op.drop_column('control', 'control_page_refs')
