"""phase5 linkedin: assisted-workflow enum values

Adds the two enum values the assisted-LinkedIn task queue needs. No new tables:
tasks are Messages (status=pending_action) and the sending identity is a
ConnectedAccount (type=linkedin, provider=assisted), both of which already exist.

Revision ID: b7d3f1902a55
Revises: a4c2e9f1b6d0
Create Date: 2026-09-06 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7d3f1902a55"
down_revision: Union[str, None] = "a4c2e9f1b6d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum-value additions aren't detected by autogenerate; add them explicitly.
    # A message parked for a human to send on an assisted channel (LinkedIn).
    op.execute("ALTER TYPE message_status ADD VALUE IF NOT EXISTS 'pending_action'")
    # A campaign member parked on an open assisted task.
    op.execute("ALTER TYPE campaign_lead_state ADD VALUE IF NOT EXISTS 'awaiting_action'")


def downgrade() -> None:
    # PostgreSQL cannot drop enum values; leaving the new values in place.
    pass
