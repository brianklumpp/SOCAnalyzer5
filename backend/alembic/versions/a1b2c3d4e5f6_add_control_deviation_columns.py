"""add control deviation columns

Revision ID: a1b2c3d4e5f6
Revises: 6f860bd14eac
Create Date: 2025-11-03 20:30:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '6f860bd14eac'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use IF NOT EXISTS to make this migration idempotent across environments
    op.execute("ALTER TABLE control ADD COLUMN IF NOT EXISTS has_deviation BOOLEAN")
    op.execute("ALTER TABLE control ADD COLUMN IF NOT EXISTS deviation_desc TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE control DROP COLUMN IF EXISTS deviation_desc")
    op.execute("ALTER TABLE control DROP COLUMN IF EXISTS has_deviation")
