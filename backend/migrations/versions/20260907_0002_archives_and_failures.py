"""Add application archives and durable asynchronous-task failure records.

Revision ID: 20260907_0002
Revises: 20260907_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0002"
down_revision: str | None = "20260907_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    application_columns = {item["name"] for item in inspector.get_columns("applications")}
    if "archived_at" not in application_columns:
        op.add_column("applications", sa.Column("archived_at", sa.DateTime(), nullable=True))
    application_indexes = {item["name"] for item in inspector.get_indexes("applications")}
    if "ix_applications_archived_at" not in application_indexes:
        op.create_index("ix_applications_archived_at", "applications", ["archived_at"])
    if "task_failures" not in inspector.get_table_names():
        op.create_table(
            "task_failures",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task_id", sa.String(length=64), nullable=True),
            sa.Column("task_name", sa.String(length=200), nullable=False),
            sa.Column("error", sa.Text(), nullable=False),
            sa.Column("traceback", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_task_failures_task_id", "task_failures", ["task_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "task_failures" in inspector.get_table_names():
        indexes = {item["name"] for item in inspector.get_indexes("task_failures")}
        if "ix_task_failures_task_id" in indexes:
            op.drop_index("ix_task_failures_task_id", table_name="task_failures")
        op.drop_table("task_failures")
    application_columns = {item["name"] for item in inspector.get_columns("applications")}
    if "archived_at" in application_columns:
        indexes = {item["name"] for item in inspector.get_indexes("applications")}
        if "ix_applications_archived_at" in indexes:
            op.drop_index("ix_applications_archived_at", table_name="applications")
        op.drop_column("applications", "archived_at")
