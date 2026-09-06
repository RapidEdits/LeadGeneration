"""Campaigns, sequence steps, and campaign membership (Phase 2 engine)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_str
from app.models.enums import (
    ApprovalMode,
    CampaignLeadState,
    CampaignState,
    Channel,
)


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"
    __table_args__ = (Index("ix_campaigns_ws_state", "workspace_id", "state"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    state: Mapped[CampaignState] = mapped_column(
        SAEnum(CampaignState, name="campaign_state"), default=CampaignState.draft, nullable=False
    )
    # Phase 2 defaults to test mode: the engine simulates sends (no real provider hit).
    test_mode: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approval_mode: Mapped[ApprovalMode] = mapped_column(
        SAEnum(ApprovalMode, name="approval_mode"), default=ApprovalMode.auto, nullable=False
    )

    # Per-channel config: {"email": {"enabled": bool, "daily_limit": int,
    #   "schedule": {"days":[0-6], "start":"HH:MM", "end":"HH:MM", "tz":"UTC"}}, ...}
    # The single source of truth for whether a channel may send — enforced server-side.
    channels: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list["CampaignStep"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="CampaignStep.order_index"
    )
    members: Mapped[list["CampaignLead"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignStep(Base, TimestampMixin):
    __tablename__ = "campaign_steps"
    __table_args__ = (
        UniqueConstraint("campaign_id", "order_index", name="uq_campaign_step_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[Channel] = mapped_column(SAEnum(Channel, name="channel"), nullable=False)
    # Days to wait after the previous step (or campaign start for step 0).
    delay_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(512))          # email only
    body_template: Mapped[str | None] = mapped_column(Text)           # {{first_name}} etc.
    ai_prompt: Mapped[str | None] = mapped_column(Text)               # Phase 4 personalization
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    campaign: Mapped["Campaign"] = relationship(back_populates="steps")


class CampaignLead(Base, TimestampMixin):
    __tablename__ = "campaign_leads"
    __table_args__ = (
        UniqueConstraint("campaign_id", "lead_id", name="uq_campaign_lead"),
        Index("ix_campaign_leads_due", "state", "next_action_at"),
        Index("ix_campaign_leads_ws", "workspace_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )

    state: Mapped[CampaignLeadState] = mapped_column(
        SAEnum(CampaignLeadState, name="campaign_lead_state"),
        default=CampaignLeadState.pending,
        nullable=False,
    )
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reason: Mapped[str | None] = mapped_column(String(255))   # last block/skip reason

    campaign: Mapped["Campaign"] = relationship(back_populates="members")
