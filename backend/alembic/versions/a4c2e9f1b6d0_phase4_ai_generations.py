"""phase4 ai: ai_generations table + ai_generate audit_action value

Revision ID: a4c2e9f1b6d0
Revises: 3f9a1c7b8d24
Create Date: 2026-09-06 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4c2e9f1b6d0"
down_revision: Union[str, None] = "3f9a1c7b8d24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New audit_action enum value (autogenerate can't detect enum-value additions).
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'ai_generate'")

    # AI generation audit table.
    op.create_table(
        "ai_generations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("lead_id", sa.String(length=36), nullable=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=True),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("facts", postgresql.JSONB(), nullable=True),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("assumptions", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_generations_workspace_id", "ai_generations", ["workspace_id"])
    op.create_index("ix_ai_generations_ws_created", "ai_generations", ["workspace_id", "created_at"])
    op.create_index("ix_ai_generations_lead", "ai_generations", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_generations_lead", table_name="ai_generations")
    op.drop_index("ix_ai_generations_ws_created", table_name="ai_generations")
    op.drop_index("ix_ai_generations_workspace_id", table_name="ai_generations")
    op.drop_table("ai_generations")
    # PostgreSQL cannot drop enum values; leaving audit_action value in place.
