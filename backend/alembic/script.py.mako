"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
% if imports:
${imports}
% endif

# revision identifiers, used by Alembic.
revision = '${up_revision}'
% if down_revision is None:
down_revision = None
% else:
down_revision = ${down_revision | repr}
% endif
% if branch_labels is None:
branch_labels = None
% else:
branch_labels = ${branch_labels | repr}
% endif
% if depends_on is None:
depends_on = None
% else:
depends_on = ${depends_on | repr}
% endif


def upgrade() -> None:
% if upgrades:
${upgrades}
% else:
    pass
% endif


def downgrade() -> None:
% if downgrades:
${downgrades}
% else:
    pass
% endif

