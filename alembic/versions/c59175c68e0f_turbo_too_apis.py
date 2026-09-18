"""TURBO ToO and observation-plan facility APIs

Revision ID: c59175c68e0f
Revises: 1830f9b2a3ad
Create Date: 2026-09-18 23:30:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c59175c68e0f"
down_revision = "1830f9b2a3ad"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE followup_apis ADD VALUE IF NOT EXISTS 'TURBOTOOAPI'")
        op.execute("ALTER TYPE followup_apis ADD VALUE IF NOT EXISTS 'TURBOMMAAPI'")


def downgrade():
    pass
