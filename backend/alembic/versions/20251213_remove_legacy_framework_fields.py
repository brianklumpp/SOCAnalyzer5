"""remove legacy framework fields

Revision ID: 20251213_remove_legacy
Revises: f8b51a47d090
Create Date: 2025-12-13

Clean up legacy framework mapping fields in favor of unified Phase 1 framework_mappings structure.
Removes TSC/COSO-specific columns that are no longer needed.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251213_remove_legacy'
down_revision = 'f8b51a47d090'
branch_labels = None
depends_on = None


def upgrade():
    # Remove legacy framework fields from control table
    op.drop_column('control', 'control_tsc_id')
    op.drop_column('control', 'control_coso_id')
    op.drop_column('control', 'control_tsc_similarity')
    op.drop_column('control', 'control_coso_similarity')
    op.drop_column('control', 'control_tsc_confidence_pct')
    op.drop_column('control', 'control_coso_confidence_pct')
    op.drop_column('control', 'control_closest_framework')
    op.drop_column('control', 'control_tsc_section')
    op.drop_column('control', 'control_coso_section')
    op.drop_column('control', 'control_tsc_mappings')
    op.drop_column('control', 'control_coso_mappings')
    
    # Remove legacy framework fields from cuec table
    op.drop_column('cuec', 'cuec_tsc_id')
    op.drop_column('cuec', 'cuec_coso_id')
    op.drop_column('cuec', 'cuec_tsc_similarity')
    op.drop_column('cuec', 'cuec_coso_similarity')
    op.drop_column('cuec', 'cuec_tsc_confidence_pct')
    op.drop_column('cuec', 'cuec_coso_confidence_pct')
    op.drop_column('cuec', 'cuec_closest_framework')
    op.drop_column('cuec', 'cuec_framework_alignment')
    op.drop_column('cuec', 'cuec_framework_alignment_id')
    op.drop_column('cuec', 'cuec_tsc_mappings')
    op.drop_column('cuec', 'cuec_coso_mappings')


def downgrade():
    # Restore legacy framework fields to control table
    op.add_column('control', sa.Column('control_tsc_id', sa.String(128), nullable=True))
    op.add_column('control', sa.Column('control_coso_id', sa.String(128), nullable=True))
    op.add_column('control', sa.Column('control_tsc_similarity', sa.Float(), nullable=True))
    op.add_column('control', sa.Column('control_coso_similarity', sa.Float(), nullable=True))
    op.add_column('control', sa.Column('control_tsc_confidence_pct', sa.Integer(), nullable=True))
    op.add_column('control', sa.Column('control_coso_confidence_pct', sa.Integer(), nullable=True))
    op.add_column('control', sa.Column('control_closest_framework', sa.String(128), nullable=True))
    op.add_column('control', sa.Column('control_tsc_section', sa.String(256), nullable=True))
    op.add_column('control', sa.Column('control_coso_section', sa.String(256), nullable=True))
    op.add_column('control', sa.Column('control_tsc_mappings', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('control', sa.Column('control_coso_mappings', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    
    # Restore legacy framework fields to cuec table
    op.add_column('cuec', sa.Column('cuec_tsc_id', sa.String(128), nullable=True))
    op.add_column('cuec', sa.Column('cuec_coso_id', sa.String(128), nullable=True))
    op.add_column('cuec', sa.Column('cuec_tsc_similarity', sa.Float(), nullable=True))
    op.add_column('cuec', sa.Column('cuec_coso_similarity', sa.Float(), nullable=True))
    op.add_column('cuec', sa.Column('cuec_tsc_confidence_pct', sa.Integer(), nullable=True))
    op.add_column('cuec', sa.Column('cuec_coso_confidence_pct', sa.Integer(), nullable=True))
    op.add_column('cuec', sa.Column('cuec_closest_framework', sa.String(128), nullable=True))
    op.add_column('cuec', sa.Column('cuec_framework_alignment', sa.String(128), nullable=True))
    op.add_column('cuec', sa.Column('cuec_framework_alignment_id', sa.String(128), nullable=True))
    op.add_column('cuec', sa.Column('cuec_tsc_mappings', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('cuec', sa.Column('cuec_coso_mappings', postgresql.JSON(astext_type=sa.Text()), nullable=True))
