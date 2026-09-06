"""Suppression list, connected accounts, audit logs, saved filters."""
from __future__ import annotations

from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_str
from app.models.enums import (
    AuditAction,
    ConnectedAccountStatus,
    ConnectedAccountType,
    SuppressionReason,
)


class SuppressionEntry(Base, TimestampMixin):
    """Global, workspace-scoped suppression. Honored across ALL campaigns/channels."""

    __tablename__ = "suppression_list"
    __table_args__ = (
        UniqueConstraint("workspace_id", "channel", "value", name="uq_suppression_entry"),
        Index("ix_suppression_ws_value", "workspace_id", "value"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)  # email | whatsapp | linkedin | all
    value: Mapped[str] = mapped_column(String(320), nullable=False)   # normalized email/phone/url
    reason: Mapped[SuppressionReason] = mapped_column(
        SAEnum(SuppressionReason, name="suppression_reason"),
        default=SuppressionReason.manual,
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text)


class ConnectedAccount(Base, TimestampMixin):
    """External sending accounts. OAuth tokens/secrets are encrypted at rest (never plaintext)."""

    __tablename__ = "connected_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[ConnectedAccountType] = mapped_column(
        SAEnum(ConnectedAccountType, name="connected_account_type"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)  # gmail | microsoft | smtp | openwa
    display_name: Mapped[str | None] = mapped_column(String(255))
    external_id: Mapped[str | None] = mapped_column(String(255))       # email address / phone / profile id
    status: Mapped[ConnectedAccountStatus] = mapped_column(
        SAEnum(ConnectedAccountStatus, name="connected_account_status"),
        default=ConnectedAccountStatus.disconnected,
        nullable=False,
    )
    encrypted_credentials: Mapped[str | None] = mapped_column(Text)    # Fernet ciphertext
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class UnsubscribeEvent(Base, TimestampMixin):
    """Audit trail of unsubscribe actions (List-Unsubscribe header or footer link).

    A matching SuppressionEntry (reason=unsubscribed) is the enforcement record honored
    by can_send; this table records the who/how/when for compliance reporting."""

    __tablename__ = "unsubscribe_events"
    __table_args__ = (Index("ix_unsub_ws_created", "workspace_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="email")
    value: Mapped[str] = mapped_column(String(320), nullable=False)  # normalized recipient
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    method: Mapped[str] = mapped_column(String(32), default="link", nullable=False)  # link | header | manual
    source_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class SavedFilter(Base, TimestampMixin):
    __tablename__ = "saved_filters"
    __table_args__ = (
        UniqueConstraint("workspace_id", "owner_id", "name", name="uq_saved_filter"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_ws_created", "workspace_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[AuditAction] = mapped_column(SAEnum(AuditAction, name="audit_action"), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
