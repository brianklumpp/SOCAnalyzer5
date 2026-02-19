"""add_objective_id_normalization_fields

Revision ID: 53c002f21ab0
Revises: 20260128_add_objective_mapping_scores
Create Date: 2026-02-02 10:47:20.661426

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '53c002f21ab0'
down_revision = '20260128_add_objective_mapping_scores'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add pattern_info to scan table (singular, not scans)
    op.add_column('scan', sa.Column('pattern_info', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Add normalization fields to control_objectives table
    op.add_column('control_objectives', sa.Column('objective_id_normalized', sa.String(), nullable=True))
    op.add_column('control_objectives', sa.Column('objective_id_original', sa.String(), nullable=True))
    
    # Create index on normalized ID for efficient sorting/searching
    op.create_index('ix_control_objectives_objective_id_normalized', 'control_objectives', ['objective_id_normalized'])
    
    # Backfill: Copy existing objective_id to both normalized and original
    # For existing data, they'll be the same initially
    op.execute("""
        UPDATE control_objectives 
        SET objective_id_normalized = objective_id,
            objective_id_original = objective_id
        WHERE objective_id IS NOT NULL
    """)


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_control_objectives_objective_id_normalized', table_name='control_objectives')
    
    # Remove columns from control_objectives
    op.drop_column('control_objectives', 'objective_id_original')
    op.drop_column('control_objectives', 'objective_id_normalized')
    
    # Remove column from scan (singular, not scans)
    op.drop_column('scan', 'pattern_info')


