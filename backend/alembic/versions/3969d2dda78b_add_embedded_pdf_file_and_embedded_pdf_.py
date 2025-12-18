"""Add embedded_pdf_file and embedded_pdf_filename columns to scan table

Revision ID: 3969d2dda78b
Revises: 2ac3574edb1e
Create Date: 2025-12-18 23:18:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3969d2dda78b'
down_revision = '2ac3574edb1e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add embedded PDF columns to scan table
    op.add_column('scan', sa.Column('embedded_pdf_file', sa.LargeBinary(), nullable=True))
    op.add_column('scan', sa.Column('embedded_pdf_filename', sa.String(length=256), nullable=True))


def downgrade() -> None:
    # Remove embedded PDF columns from scan table
    op.drop_column('scan', 'embedded_pdf_filename')
    op.drop_column('scan', 'embedded_pdf_file')
