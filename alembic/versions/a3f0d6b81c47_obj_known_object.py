"""obj known_object

Revision ID: a3f0d6b81c47
Revises: e8c2a5d71b40
Create Date: 2026-09-22 22:20:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "a3f0d6b81c47"
down_revision = "e8c2a5d71b40"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "objs",
        sa.Column(
            "known_object", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade():
    op.drop_column("objs", "known_object")
