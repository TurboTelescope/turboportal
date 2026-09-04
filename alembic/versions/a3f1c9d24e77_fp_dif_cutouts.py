"""Per-epoch forced-photometry DIF cutouts

Revision ID: a3f1c9d24e77
Revises: e7c94b2d1a63
Create Date: 2026-09-04 21:40:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a3f1c9d24e77"
down_revision = "e7c94b2d1a63"
branch_labels = None
depends_on = None


def upgrade():
    # Safe inside a transaction on PG12+ as long as the new label isn't used
    # in the same transaction, which it isn't here.
    op.execute("ALTER TYPE thumbnail_types ADD VALUE IF NOT EXISTS 'fp_dif'")
    op.add_column(
        "thumbnails", sa.Column("photometry_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "thumbnails_photometry_id_fkey",
        "thumbnails",
        "photometry",
        ["photometry_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_thumbnails_photometry_id"),
        "thumbnails",
        ["photometry_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_thumbnails_photometry_id"), table_name="thumbnails")
    op.drop_constraint(
        "thumbnails_photometry_id_fkey", "thumbnails", type_="foreignkey"
    )
    op.drop_column("thumbnails", "photometry_id")
    # Postgres cannot drop a single enum label; 'fp_dif' is left in place.
