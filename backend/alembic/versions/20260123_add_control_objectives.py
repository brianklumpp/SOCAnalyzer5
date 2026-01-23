"""Add control objectives and mappings tables

Revision ID: 20260123_add_control_objectives
Revises: 20260120_add_scan_history_optimizations
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260123_add_control_objectives'
down_revision = '20260120_add_scan_history_optimizations'
branch_labels = None
depends_on = None


def upgrade():
    # Create control_objectives table
    op.create_table(
        'control_objectives',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('scan_id', sa.Integer(), nullable=False),
        sa.Column('objective_id', sa.String(length=128), nullable=True),
        sa.Column('objective_text', sa.Text(), nullable=False),
        sa.Column('keyword_confidence', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('distance_confidence', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('gpt_confidence', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('alignment_confidence', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('format_confidence', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('final_confidence', sa.Float(), nullable=False),
        sa.Column('confidence_calc', sa.Text(), nullable=True),
        sa.Column('gpt_reasoning', sa.Text(), nullable=True),
        sa.Column('page_refs', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('line_ref', sa.Integer(), nullable=True),
        sa.Column('source_context', sa.Text(), nullable=True),
        sa.Column('extraction_method', sa.String(length=32), nullable=True),
        sa.Column('section_heading', sa.String(length=256), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['scan_id'], ['scan.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ),
    )
    
    # Create indexes
    op.create_index('ix_control_objectives_scan_id', 'control_objectives', ['scan_id'])
    op.create_index('ix_control_objectives_objective_id', 'control_objectives', ['objective_id'])
    op.create_index('ix_control_objectives_final_confidence', 'control_objectives', ['final_confidence'])
    
    # Create control_objective_mappings table (junction table)
    op.create_table(
        'control_objective_mappings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('control_id', sa.Integer(), nullable=False),
        sa.Column('objective_id', sa.Integer(), nullable=False),
        sa.Column('mapping_confidence', sa.Float(), nullable=True, server_default='1.0'),
        sa.Column('mapping_method', sa.String(length=32), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['control_id'], ['control.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['objective_id'], ['control_objectives.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    )
    
    # Create indexes
    op.create_index('ix_control_objective_mappings_control_id', 'control_objective_mappings', ['control_id'])
    op.create_index('ix_control_objective_mappings_objective_id', 'control_objective_mappings', ['objective_id'])


def downgrade():
    # Drop tables in reverse order (junction table first due to foreign keys)
    op.drop_index('ix_control_objective_mappings_objective_id', table_name='control_objective_mappings')
    op.drop_index('ix_control_objective_mappings_control_id', table_name='control_objective_mappings')
    op.drop_table('control_objective_mappings')
    
    op.drop_index('ix_control_objectives_final_confidence', table_name='control_objectives')
    op.drop_index('ix_control_objectives_objective_id', table_name='control_objectives')
    op.drop_index('ix_control_objectives_scan_id', table_name='control_objectives')
    op.drop_table('control_objectives')
