"""add_confidence_weights_and_review_tables

Revision ID: 2d834bf34316
Revises: ddd7e42ccd82
Create Date: 2025-11-14 13:29:18.593180

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2d834bf34316'
down_revision = 'ddd7e42ccd82'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create confidence_weights table
    op.create_table(
        'confidence_weights',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization', sa.String(256), nullable=True),
        sa.Column('gpt_weight', sa.Float(), nullable=False, server_default='0.25'),
        sa.Column('pattern_weight', sa.Float(), nullable=False, server_default='0.20'),
        sa.Column('structure_weight', sa.Float(), nullable=False, server_default='0.20'),
        sa.Column('framework_weight', sa.Float(), nullable=False, server_default='0.20'),
        sa.Column('deviation_weight', sa.Float(), nullable=False, server_default='0.15'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    
    # Create unique constraint on organization
    op.create_index('idx_confidence_weights_org', 'confidence_weights', ['organization'], unique=True)
    
    # Insert global default weights
    op.execute("""
        INSERT INTO confidence_weights (organization, gpt_weight, pattern_weight, structure_weight, framework_weight, deviation_weight)
        VALUES (NULL, 0.25, 0.20, 0.20, 0.20, 0.15)
    """)
    
    # Create confidence_weight_audit table
    op.create_table(
        'confidence_weight_audit',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('weight_config_id', sa.Integer(), nullable=True),
        sa.Column('organization', sa.String(256), nullable=True),
        sa.Column('changed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('old_weights', sa.JSON(), nullable=True),
        sa.Column('new_weights', sa.JSON(), nullable=False),
        sa.Column('change_reason', sa.Text(), nullable=True),
        sa.Column('change_type', sa.String(32), nullable=False),
        sa.Column('changed_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    
    # Create index on changed_at for audit queries
    op.create_index('idx_weight_audit_changed_at', 'confidence_weight_audit', ['changed_at'])
    op.create_index('idx_weight_audit_org', 'confidence_weight_audit', ['organization'])
    
    # Create control_review table
    op.create_table(
        'control_review',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('control_id', sa.Integer(), nullable=False),
        sa.Column('scan_id', sa.Integer(), nullable=False),
        sa.Column('organization', sa.String(256), nullable=True),
        sa.Column('reviewed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('review_status', sa.String(32), nullable=False),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('low_factor_flags', sa.JSON(), nullable=True),
        sa.Column('final_confidence_at_review', sa.Float(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    
    # Create indexes for review queries
    op.create_index('idx_control_review_scan', 'control_review', ['scan_id', 'review_status'])
    op.create_index('idx_control_review_org', 'control_review', ['organization'])
    op.create_index('idx_control_review_status', 'control_review', ['review_status'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('idx_control_review_status', 'control_review')
    op.drop_index('idx_control_review_org', 'control_review')
    op.drop_index('idx_control_review_scan', 'control_review')
    op.drop_table('control_review')
    
    op.drop_index('idx_weight_audit_org', 'confidence_weight_audit')
    op.drop_index('idx_weight_audit_changed_at', 'confidence_weight_audit')
    op.drop_table('confidence_weight_audit')
    
    op.drop_index('idx_confidence_weights_org', 'confidence_weights')
    op.drop_table('confidence_weights')

