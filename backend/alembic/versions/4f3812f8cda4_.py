"""merge multiple heads

Revision ID: 4f3812f8cda4
Revises: 20251114000723, a1b2c3d4e5f6
Create Date: 2025-11-14 00:25:14.326986

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4f3812f8cda4'
down_revision = ('20251114000723', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

