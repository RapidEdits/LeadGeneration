"""Messages and normalized message events (unified outreach timeline)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_str
from app.models.enums import (
    Channel,
    MessageDirection,
    MessageEventType,
    MessageStatus,
    Provenance,
)


def tracking_token() -> str:
    """Unguessable capability token used in public open/click/unsubscribe URLs."""
    import secrets

    return secrets.token_urlsafe(24)


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_ws_created", "workspace_id", "created_at"),
        Index("ix_messages_lead", "lead_id"),
        Index("ix_messages_tracking_id", "tracking_id", unique=True),
        Index("ix_messages_provider_msg", "provider_message_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    campaign_lead_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_leads.id", ondelete="SET NULL")
    )
    step_id: Mapped[str | None] = mapped_column(ForeignKey("campaign_steps.id", ondelete="SET NULL"))

    channel: Mapped[Channel] = mapped_column(SAEnum(Channel, name="channel"), nullable=False)
    direction: Mapped[MessageDirection] = mapped_column(
        SAEnum(MessageDirection, name="message_direction"), nullable=False
    )
    status: Mapped[MessageStatus] = mapped_column(
        SAEnum(MessageStatus, name="message_status"), default=MessageStatus.queued, nullable=False
    )
    subject: Mapped[str | None] = mapped_column(String(512))
    body: Mapped[str | None] = mapped_column(Text)
    to_address: Mapped[str | None] = mapped_column(String(320))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    # Opaque capability token embedded in open-pixel / click / unsubscribe URLs.
    tracking_id: Mapped[str | None] = mapped_column(String(64), default=tracking_token)
    # RFC822 Message-ID / In-Reply-To threading, for reply attribution on inbound poll.
    rfc_message_id: Mapped[str | None] = mapped_column(String(512))
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class MessageEvent(Base, TimestampMixin):
    """Normalized provider events (spec §19/§39) with provenance."""

    __tablename__ = "message_events"
    __table_args__ = (Index("ix_message_events_msg", "message_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    type: Mapped[MessageEventType] = mapped_column(
        SAEnum(MessageEventType, name="message_event_type"), nullable=False
    )
    provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), default=Provenance.observed, nullable=False
    )
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
