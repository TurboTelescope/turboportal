"""TURBO source requests

Revision ID: b7d3f1a9c5e2
Revises: a3f0d6b81c47
Create Date: 2026-10-12 06:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7d3f1a9c5e2"
down_revision = "a3f0d6b81c47"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "turbo_source_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("modified", sa.DateTime(), nullable=False),
        sa.Column("allocation_id", sa.Integer(), nullable=False),
        sa.Column("requester_id", sa.Integer(), nullable=True),
        sa.Column("star", sa.String(), nullable=True),
        sa.Column("ra", sa.Float(), nullable=True),
        sa.Column("dec", sa.Float(), nullable=True),
        sa.Column("radius", sa.Float(), nullable=False),
        sa.Column("group_ids", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("obj_id", sa.String(), nullable=True),
        sa.Column("n_points", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["allocation_id"], ["allocations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["obj_id"], ["objs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("allocation_id", "requester_id", "status", "obj_id"):
        op.create_index(
            op.f(f"ix_turbo_source_requests_{column}"),
            "turbo_source_requests",
            [column],
            unique=False,
        )


def downgrade():
    op.drop_table("turbo_source_requests")
