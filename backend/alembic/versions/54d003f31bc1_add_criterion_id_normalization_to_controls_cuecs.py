"""add criterion_id normalization to controls and cuecs

Revision ID: 54d003f31bc1
Revises: 53c002f21ab0
Create Date: 2025-02-02 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '54d003f31bc1'
down_revision = '53c002f21ab0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Extend normalization to Controls and CUECs for their primary_criterion_id fields.
    This ensures consistent storage, sorting, and matching across all entities that reference framework criteria.
    """
    # Add normalization fields to control table
    op.add_column('control', sa.Column('primary_criterion_id_normalized', sa.String(128), nullable=True,
                                       comment='Normalized criterion ID for consistent display/sorting'))
    op.add_column('control', sa.Column('primary_criterion_id_original', sa.String(128), nullable=True,
                                       comment='Original criterion ID format from report for accurate searching'))
    
    # Add normalization fields to cuec table
    op.add_column('cuec', sa.Column('primary_criterion_id_normalized', sa.String(128), nullable=True,
                                    comment='Normalized criterion ID for consistent display/sorting'))
    op.add_column('cuec', sa.Column('primary_criterion_id_original', sa.String(128), nullable=True,
                                    comment='Original criterion ID format from report for accurate searching'))
    
    # Create indexes on normalized IDs for efficient sorting/searching
    op.create_index('ix_control_primary_criterion_id_normalized', 'control', ['primary_criterion_id_normalized'])
    op.create_index('ix_cuec_primary_criterion_id_normalized', 'cuec', ['primary_criterion_id_normalized'])
    
    # Backfill: Normalize existing primary_criterion_id values
    # Remove spaces before dots and dashes, collapse multiple spaces
    op.execute("""
        UPDATE control
        SET primary_criterion_id_normalized = REGEXP_REPLACE(
                REGEXP_REPLACE(primary_criterion_id, '\\s+([.-])', '\\1', 'g'),
                '\\s+', ' ', 'g'
            ),
            primary_criterion_id_original = primary_criterion_id
        WHERE primary_criterion_id IS NOT NULL
    """)
    
    op.execute("""
        UPDATE cuec
        SET primary_criterion_id_normalized = REGEXP_REPLACE(
                REGEXP_REPLACE(primary_criterion_id, '\\s+([.-])', '\\1', 'g'),
                '\\s+', ' ', 'g'
            ),
            primary_criterion_id_original = primary_criterion_id
        WHERE primary_criterion_id IS NOT NULL
    """)


def downgrade() -> None:
    """
    Remove normalization fields from controls and cuecs.
    """
    # Remove indexes
    op.drop_index('ix_cuec_primary_criterion_id_normalized', table_name='cuec')
    op.drop_index('ix_control_primary_criterion_id_normalized', table_name='control')
    
    # Remove columns from cuec
    op.drop_column('cuec', 'primary_criterion_id_original')
    op.drop_column('cuec', 'primary_criterion_id_normalized')
    
    # Remove columns from control
    op.drop_column('control', 'primary_criterion_id_original')
    op.drop_column('control', 'primary_criterion_id_normalized')
