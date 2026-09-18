"""sharing service submission at_type

Revision ID: 1830f9b2a3ad
Revises: cc46e57df853
Create Date: 2026-09-18 21:10:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "1830f9b2a3ad"
down_revision = "cc46e57df853"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sharingservicesubmissions",
        sa.Column("at_type", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )


def downgrade():
    op.drop_column("sharingservicesubmissions", "at_type")
