"""add campaign audit_action values

Revision ID: e810666fcc2e
Revises: 0d0e908bfe22
Create Date: 2026-09-05 11:33:20.163284
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e810666fcc2e'
down_revision: Union[str, None] = '0d0e908bfe22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_VALUES = [
    "campaign_launch",
    "campaign_pause",
    "campaign_resume",
    "campaign_complete",
    "message_sent",
]


def upgrade() -> None:
    # Alembic autogenerate doesn't detect enum-value additions; add them explicitly.
    for value in NEW_VALUES:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; no-op.
    pass
