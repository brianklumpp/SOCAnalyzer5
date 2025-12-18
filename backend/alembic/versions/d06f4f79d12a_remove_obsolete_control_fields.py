"""remove_obsolete_control_fields

Revision ID: d06f4f79d12a
Revises: 94ab857cec4b
Create Date: 2025-12-16 09:25:17.562248

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd06f4f79d12a'
down_revision = '94ab857cec4b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove obsolete field from control table
    op.drop_column('control', 'control_soc_domain')


def downgrade() -> None:
    # Restore obsolete field if needed to rollback
    op.add_column('control', sa.Column('control_soc_domain', sa.VARCHAR(length=128), nullable=True))

