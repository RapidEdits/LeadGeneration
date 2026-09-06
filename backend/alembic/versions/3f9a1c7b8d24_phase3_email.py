"""phase3 email: tracking columns, unsubscribe_events, new message_event_type values

Revision ID: 3f9a1c7b8d24
Revises: e810666fcc2e
Create Date: 2026-09-05 12:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3f9a1c7b8d24"
down_revision: Union[str, None] = "e810666fcc2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_EVENT_VALUES = ["clicked", "unsubscribed", "complained"]


def upgrade() -> None:
    # 1. New message_event_type enum values (autogenerate can't detect these).
    for value in NEW_EVENT_VALUES:
        op.execute(f"ALTER TYPE message_event_type ADD VALUE IF NOT EXISTS '{value}'")

    # 2. Tracking + RFC threading columns on messages.
    op.add_column("messages", sa.Column("tracking_id", sa.String(length=64), nullable=True))
    op.add_column("messages", sa.Column("rfc_message_id", sa.String(length=512), nullable=True))
    op.create_index("ix_messages_tracking_id", "messages", ["tracking_id"], unique=True)
    op.create_index("ix_messages_provider_msg", "messages", ["provider_message_id"], unique=False)

    # 3. Unsubscribe audit trail.
    op.create_table(
        "unsubscribe_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="email"),
        sa.Column("value", sa.String(length=320), nullable=False),
        sa.Column("lead_id", sa.String(length=36), nullable=True),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=False, server_default="link"),
        sa.Column("source_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_unsubscribe_events_workspace_id", "unsubscribe_events", ["workspace_id"])
    op.create_index("ix_unsub_ws_created", "unsubscribe_events", ["workspace_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_unsub_ws_created", table_name="unsubscribe_events")
    op.drop_index("ix_unsubscribe_events_workspace_id", table_name="unsubscribe_events")
    op.drop_table("unsubscribe_events")
    op.drop_index("ix_messages_provider_msg", table_name="messages")
    op.drop_index("ix_messages_tracking_id", table_name="messages")
    op.drop_column("messages", "rfc_message_id")
    op.drop_column("messages", "tracking_id")
    # PostgreSQL cannot drop enum values; leaving message_event_type values in place.
