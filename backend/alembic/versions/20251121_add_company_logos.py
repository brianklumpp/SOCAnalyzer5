"""Add company logo fields

Revision ID: 20251121_add_company_logos
Revises: 20251120_report_type_detections
Create Date: 2025-11-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251121_add_company_logos'
down_revision = '20251120_report_type_detections'
branch_labels = None
depends_on = None


def upgrade():
    """Add company_domain and logo_url columns to company table."""
    op.add_column('company', sa.Column('company_domain', sa.String(256), nullable=True))
    op.add_column('company', sa.Column('logo_url', sa.String(512), nullable=True))
    
    # Create index on company_domain for faster lookups
    op.create_index('ix_company_domain', 'company', ['company_domain'])


def downgrade():
    """Remove company logo fields."""
    op.drop_index('ix_company_domain', table_name='company')
    op.drop_column('company', 'logo_url')
    op.drop_column('company', 'company_domain')
