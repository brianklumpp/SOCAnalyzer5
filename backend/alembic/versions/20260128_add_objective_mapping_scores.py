"""Add objective mapping scores and CUEC mappings table

Revision ID: 20260128_add_objective_mapping_scores
Revises: 20260123_add_control_objectives
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260128_add_objective_mapping_scores'
down_revision = '20260123_add_control_objectives'
branch_labels = None
depends_on = None


def upgrade():
    # Add score fields to control_objective_mappings
    op.add_column('control_objective_mappings', sa.Column('page_proximity_score', sa.Float(), nullable=True))
    op.add_column('control_objective_mappings', sa.Column('line_proximity_score', sa.Float(), nullable=True))
    op.add_column('control_objective_mappings', sa.Column('gpt_alignment_score', sa.Float(), nullable=True))
    op.add_column('control_objective_mappings', sa.Column('id_alignment_score', sa.Float(), nullable=True))

    # Create cuec_objective_mappings table
    op.create_table(
        'cuec_objective_mappings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('cuec_id', sa.Integer(), nullable=False),
        sa.Column('objective_id', sa.Integer(), nullable=False),
        sa.Column('mapping_confidence', sa.Float(), nullable=True, server_default='1.0'),
        sa.Column('page_proximity_score', sa.Float(), nullable=True),
        sa.Column('line_proximity_score', sa.Float(), nullable=True),
        sa.Column('gpt_alignment_score', sa.Float(), nullable=True),
        sa.Column('mapping_method', sa.String(length=32), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['cuec_id'], ['cuec.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['objective_id'], ['control_objectives.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cuec_objective_mappings_cuec_id', 'cuec_objective_mappings', ['cuec_id'])
    op.create_index('ix_cuec_objective_mappings_objective_id', 'cuec_objective_mappings', ['objective_id'])


def downgrade():
    op.drop_index('ix_cuec_objective_mappings_objective_id', table_name='cuec_objective_mappings')
    op.drop_index('ix_cuec_objective_mappings_cuec_id', table_name='cuec_objective_mappings')
    op.drop_table('cuec_objective_mappings')

    op.drop_column('control_objective_mappings', 'id_alignment_score')
    op.drop_column('control_objective_mappings', 'gpt_alignment_score')
    op.drop_column('control_objective_mappings', 'line_proximity_score')
    op.drop_column('control_objective_mappings', 'page_proximity_score')
