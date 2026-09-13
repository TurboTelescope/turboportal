"""post-merge no-op

A mergepoint revision's `alembic current --verbose` line ends in
"(head) (mergepoint)", not "(head)" -- baselayer's migration_manager checks
for a literal "(head)" suffix, so it never considers a mergepoint head
migrated. This trivial revision on top gives it a normal, non-mergepoint
head to land on.

Revision ID: cc46e57df853
Revises: e494de70485a
Create Date: 2026-09-13 03:35:00.000000

"""

# revision identifiers, used by Alembic.
revision = "cc46e57df853"
down_revision = "e494de70485a"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
