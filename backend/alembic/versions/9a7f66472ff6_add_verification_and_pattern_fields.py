"""add_verification_and_pattern_fields

Revision ID: 9a7f66472ff6
Revises: 20250207000001
Create Date: 2025-11-14 12:47:26.614540

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9a7f66472ff6'
down_revision = '20250207000001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add verification and pattern scoring fields to control table
    op.add_column('control', sa.Column('verification_status', sa.String(32), nullable=True))
    op.add_column('control', sa.Column('verification_metadata', sa.JSON(), nullable=True))
    op.add_column('control', sa.Column('pattern_confidence', sa.Float(), nullable=True))
    op.add_column('control', sa.Column('final_confidence', sa.Float(), nullable=True))
    
    # Create control_pattern table
    op.create_table(
        'control_pattern',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization', sa.String(256), nullable=False),
        sa.Column('pattern', sa.String(128), nullable=False),
        sa.Column('frequency', sa.Integer(), default=1),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('scan_ids', sa.JSON(), nullable=True)
    )
    
    # Create index for efficient pattern lookups
    op.create_index('idx_pattern_org', 'control_pattern', ['organization', 'pattern'])
    
    # Create pattern_review_queue table
    op.create_table(
        'pattern_review_queue',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization', sa.String(256), nullable=False),
        sa.Column('pattern1', sa.String(128), nullable=False),
        sa.Column('pattern2', sa.String(128), nullable=False),
        sa.Column('merged_pattern', sa.String(128), nullable=False),
        sa.Column('similarity_score', sa.Float(), nullable=False),
        sa.Column('status', sa.String(32), default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.String(128), nullable=True)
    )


def downgrade() -> None:
    # Drop pattern_review_queue table
    op.drop_table('pattern_review_queue')
    
    # Drop control_pattern table and index
    op.drop_index('idx_pattern_org', 'control_pattern')
    op.drop_table('control_pattern')
    
    # Remove verification fields from control table
    op.drop_column('control', 'final_confidence')
    op.drop_column('control', 'pattern_confidence')
    op.drop_column('control', 'verification_metadata')
    op.drop_column('control', 'verification_status')

