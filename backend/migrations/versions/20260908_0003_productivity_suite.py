"""Add interview rounds and productivity metadata.

Revision ID: 20260908_0003
Revises: 20260907_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0003"
down_revision: str | None = "20260907_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    resume_columns = {item["name"] for item in inspector.get_columns("resume_versions")}
    if "content_text" not in resume_columns:
        op.add_column("resume_versions", sa.Column("content_text", sa.Text(), nullable=True))
    app_columns = {item["name"] for item in inspector.get_columns("applications")}
    if "tags" not in app_columns:
        op.add_column("applications", sa.Column("tags", sa.JSON(), nullable=True))
        op.execute(sa.text("UPDATE applications SET tags = '[]' WHERE tags IS NULL"))
        op.alter_column("applications", "tags", existing_type=sa.JSON(), nullable=False)
    if "custom_fields" not in app_columns:
        op.add_column("applications", sa.Column("custom_fields", sa.JSON(), nullable=True))
        op.execute(sa.text("UPDATE applications SET custom_fields = '{}' WHERE custom_fields IS NULL"))
        op.alter_column("applications", "custom_fields", existing_type=sa.JSON(), nullable=False)
    if "interview_rounds" not in inspector.get_table_names():
        op.create_table(
            "interview_rounds",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("application_id", sa.Integer(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
            sa.Column("round_name", sa.String(120), nullable=False),
            sa.Column("interview_type", sa.String(40), nullable=False),
            sa.Column("scheduled_at", sa.DateTime(), nullable=False),
            sa.Column("duration_minutes", sa.Integer(), nullable=False),
            sa.Column("location", sa.String(500), nullable=True),
            sa.Column("interviewer", sa.String(160), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("outcome", sa.String(40), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_interview_rounds_user_id", "interview_rounds", ["user_id"])
        op.create_index("ix_interview_rounds_application_id", "interview_rounds", ["application_id"])
        op.create_index("ix_interviews_owner_scheduled", "interview_rounds", ["user_id", "scheduled_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "interview_rounds" in inspector.get_table_names():
        op.drop_table("interview_rounds")
    app_columns = {item["name"] for item in inspector.get_columns("applications")}
    if "custom_fields" in app_columns:
        op.drop_column("applications", "custom_fields")
    if "tags" in app_columns:
        op.drop_column("applications", "tags")
    resume_columns = {item["name"] for item in inspector.get_columns("resume_versions")}
    if "content_text" in resume_columns:
        op.drop_column("resume_versions", "content_text")
