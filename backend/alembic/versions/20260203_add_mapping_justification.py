"""Add mapping justification and objective confidence boost

Revision ID: 20260203_add_mapping_justification
Revises: 54d003f31bc1
Create Date: 2026-02-03

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260203_add_mapping_justification'
down_revision = '54d003f31bc1'
branch_labels = None
depends_on = None


def upgrade():
    # Add mapping_justification to control_objective_mappings
    op.add_column('control_objective_mappings', sa.Column('mapping_justification', sa.Text(), nullable=True))
    
    # Add objective_gpt_confidence_boost to control_objective_mappings
    op.add_column('control_objective_mappings', sa.Column('objective_gpt_confidence_boost', sa.Float(), nullable=True))
    
    # Add mapping_justification to cuec_objective_mappings (for consistency)
    op.add_column('cuec_objective_mappings', sa.Column('mapping_justification', sa.Text(), nullable=True))
    op.add_column('cuec_objective_mappings', sa.Column('objective_gpt_confidence_boost', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('cuec_objective_mappings', 'objective_gpt_confidence_boost')
    op.drop_column('cuec_objective_mappings', 'mapping_justification')
    op.drop_column('control_objective_mappings', 'objective_gpt_confidence_boost')
    op.drop_column('control_objective_mappings', 'mapping_justification')
