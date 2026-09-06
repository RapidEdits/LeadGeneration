"""phase7 crm: tasks + lead_notes

Revision ID: c9e4a2b17f38
Revises: b7d3f1902a55
Create Date: 2026-09-06 13:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9e4a2b17f38"
down_revision: Union[str, None] = "b7d3f1902a55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False so op.create_table doesn't re-emit CREATE TYPE — we create the
# enums explicitly (checkfirst) below, per the project's reused-enum migration gotcha.
task_type = postgresql.ENUM("todo", "call", "email", "meeting", "linkedin",
                            name="task_type", create_type=False)
task_status = postgresql.ENUM("open", "done", "cancelled", name="task_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    task_type.create(bind, checkfirst=True)
    task_status.create(bind, checkfirst=True)

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("lead_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("assignee_id", sa.String(length=36), nullable=True),
        sa.Column("type", task_type, nullable=False, server_default="todo"),
        sa.Column("status", task_status, nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_tasks_workspace_id", "tasks", ["workspace_id"])
    op.create_index("ix_tasks_ws_status_due", "tasks", ["workspace_id", "status", "due_at"])
    op.create_index("ix_tasks_lead", "tasks", ["lead_id"])
    op.create_index("ix_tasks_assignee", "tasks", ["assignee_id"])

    op.create_table(
        "lead_notes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("lead_id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_lead_notes_workspace_id", "lead_notes", ["workspace_id"])
    op.create_index("ix_lead_notes_lead_created", "lead_notes", ["lead_id", "created_at"])


def downgrade() -> None:
    op.drop_table("lead_notes")
    op.drop_index("ix_tasks_assignee", table_name="tasks")
    op.drop_index("ix_tasks_lead", table_name="tasks")
    op.drop_index("ix_tasks_ws_status_due", table_name="tasks")
    op.drop_index("ix_tasks_workspace_id", table_name="tasks")
    op.drop_table("tasks")
    task_status.drop(op.get_bind(), checkfirst=True)
    task_type.drop(op.get_bind(), checkfirst=True)
