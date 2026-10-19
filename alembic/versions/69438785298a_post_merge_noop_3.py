"""post-merge no-op

Same reason as cc46e57df853: baselayer's migration_manager needs a head that
is not a mergepoint.

Revision ID: 69438785298a
Revises: 69ef5043e630
Create Date: 2026-10-19 06:20:00.000000

"""

# revision identifiers, used by Alembic.
revision = "69438785298a"
down_revision = "69ef5043e630"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
