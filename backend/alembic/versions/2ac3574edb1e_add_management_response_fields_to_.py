"""add_management_response_fields_to_control

Revision ID: 2ac3574edb1e
Revises: d06f4f79d12a
Create Date: 2025-12-18 02:02:55.744096

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2ac3574edb1e'
down_revision = 'd06f4f79d12a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add management response fields to control table
    op.add_column('control', sa.Column('management_response_text', sa.Text(), nullable=True))
    op.add_column('control', sa.Column('management_response_page_refs', sa.JSON(), nullable=True))
    op.add_column('control', sa.Column('management_response_line_ref', sa.Integer(), nullable=True))
    op.add_column('control', sa.Column('management_response_confidence', sa.Float(), nullable=True))
    op.add_column('control', sa.Column('response_detection_method', sa.String(length=32), nullable=True))


def downgrade() -> None:
    # Remove management response fields from control table
    op.drop_column('control', 'response_detection_method')
    op.drop_column('control', 'management_response_confidence')
    op.drop_column('control', 'management_response_line_ref')
    op.drop_column('control', 'management_response_page_refs')
    op.drop_column('control', 'management_response_text')

