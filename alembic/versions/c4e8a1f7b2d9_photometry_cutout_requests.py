"""Per-point photometry cutout requests

Revision ID: c4e8a1f7b2d9
Revises: a3f1c9d24e77
Create Date: 2026-09-12 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c4e8a1f7b2d9"
down_revision = "a3f1c9d24e77"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE thumbnail_types RENAME VALUE 'fp_dif' TO 'dif'")
    op.create_table(
        "photometry_cutout_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("modified", sa.DateTime(), nullable=False),
        sa.Column("photometry_id", sa.BigInteger(), nullable=False),
        sa.Column("requester_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["photometry_id"], ["photometry.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_photometry_cutout_requests_photometry_id"),
        "photometry_cutout_requests",
        ["photometry_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_photometry_cutout_requests_requester_id"),
        "photometry_cutout_requests",
        ["requester_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_photometry_cutout_requests_status"),
        "photometry_cutout_requests",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_photometry_cutout_requests_status"),
        table_name="photometry_cutout_requests",
    )
    op.drop_index(
        op.f("ix_photometry_cutout_requests_requester_id"),
        table_name="photometry_cutout_requests",
    )
    op.drop_index(
        op.f("ix_photometry_cutout_requests_photometry_id"),
        table_name="photometry_cutout_requests",
    )
    op.drop_table("photometry_cutout_requests")
    op.execute("ALTER TYPE thumbnail_types RENAME VALUE 'dif' TO 'fp_dif'")
