"""post-merge no-op

Same reason as cc46e57df853: a mergepoint revision's
`alembic current --verbose` line ends in "(head) (mergepoint)", and
baselayer's migration_manager checks for a literal "(head)" suffix, so it
never considers a mergepoint head migrated. This gives it a normal head.

Revision ID: e8c2a5d71b40
Revises: d5b3e9a17c24
Create Date: 2026-09-22 05:25:00.000000

"""

# revision identifiers, used by Alembic.
revision = "e8c2a5d71b40"
down_revision = "d5b3e9a17c24"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
