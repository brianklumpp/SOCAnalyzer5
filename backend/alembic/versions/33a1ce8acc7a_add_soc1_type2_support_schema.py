"""add_soc1_type2_support_schema

Revision ID: 33a1ce8acc7a
Revises: 20251119_multi_page_refs
Create Date: 2025-11-19 20:58:12.263492

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '33a1ce8acc7a'
down_revision = '20251119_multi_page_refs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create report_type enum
    report_type_enum = postgresql.ENUM('SOC1', 'SOC2', 'COMBINED', name='reporttype')
    report_type_enum.create(op.get_bind(), checkfirst=True)
    
    # Add columns to scan table
    op.add_column('scan', sa.Column('report_type', sa.Enum('SOC1', 'SOC2', 'COMBINED', name='reporttype'), 
                                     nullable=False, server_default='SOC2'))
    op.add_column('scan', sa.Column('as_of_date', sa.DateTime(), nullable=True))
    op.add_column('scan', sa.Column('progress_status', sa.String(length=128), nullable=True))
    op.add_column('scan', sa.Column('elapsed_seconds', sa.Float(), nullable=True))
    
    # Add columns to control table
    op.add_column('control', sa.Column('financial_assertions', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('control', sa.Column('framework_category', sa.String(length=32), nullable=True))


def downgrade() -> None:
    # Remove columns from control table
    op.drop_column('control', 'framework_category')
    op.drop_column('control', 'financial_assertions')
    
    # Remove columns from scan table
    op.drop_column('scan', 'elapsed_seconds')
    op.drop_column('scan', 'progress_status')
    op.drop_column('scan', 'as_of_date')
    op.drop_column('scan', 'report_type')
    
    # Drop enum type
    report_type_enum = postgresql.ENUM('SOC1', 'SOC2', 'COMBINED', name='reporttype')
    report_type_enum.drop(op.get_bind(), checkfirst=True)

