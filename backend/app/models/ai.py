"""AI generation audit — every model output is recorded here (spec: facts-used +
assumptions), so any AI-influenced decision is traceable and reviewable."""
from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_str


class AIGeneration(Base, TimestampMixin):
    __tablename__ = "ai_generations"
    __table_args__ = (
        Index("ix_ai_generations_ws_created", "workspace_id", "created_at"),
        Index("ix_ai_generations_lead", "lead_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    kind: Mapped[str] = mapped_column(String(48), nullable=False)     # qualify_lead, generate_email, ...
    model: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)  # ok|unknown|error

    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))

    facts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)          # exact input snapshot
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)         # structured result
    assumptions: Mapped[list[Any] | None] = mapped_column(JSONB)         # model-flagged assumptions
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens: Mapped[int | None] = mapped_column(Integer)
