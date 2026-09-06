"""Companies, leads, lead sources, tags, and the lead<->tag association."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_str
from app.models.enums import CampaignStatus, LeadStatus, Provenance

if TYPE_CHECKING:
    from app.models.user import Workspace


class Company(Base, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_ws_domain", "workspace_id", "domain"),
        Index("ix_companies_ws_name", "workspace_id", "name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(512))
    industry: Mapped[str | None] = mapped_column(String(255))
    size: Mapped[str | None] = mapped_column(String(64))          # e.g. "11-50"
    location: Mapped[str | None] = mapped_column(String(255))
    linkedin_url: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    enrichment: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    workspace: Mapped["Workspace"] = relationship(back_populates="companies")
    leads: Mapped[list["Lead"]] = relationship(back_populates="company")


class LeadSource(Base, TimestampMixin):
    __tablename__ = "lead_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)   # csv | manual | api | crm
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    leads: Mapped[list["Lead"]] = relationship(back_populates="source")


class Tag(Base, TimestampMixin):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_tag_ws_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str | None] = mapped_column(String(24))


class LeadTag(Base):
    __tablename__ = "lead_tags"
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class Lead(Base, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (
        # Dedup-supporting indexes (workspace-scoped).
        Index("ix_leads_ws_email", "workspace_id", "email"),
        Index("ix_leads_ws_linkedin", "workspace_id", "linkedin_url"),
        Index("ix_leads_ws_phone", "workspace_id", "phone"),
        Index("ix_leads_ws_name_company", "workspace_id", "full_name", "company_id"),
        Index("ix_leads_ws_status", "workspace_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("lead_sources.id", ondelete="SET NULL")
    )

    # Identity
    full_name: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    linkedin_url: Mapped[str | None] = mapped_column(String(512))
    location: Mapped[str | None] = mapped_column(String(255))

    # Scoring / qualification (populated in Phase 4)
    score: Mapped[float | None] = mapped_column(Float)
    ai_qualification: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    email_provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), default=Provenance.unknown, nullable=False
    )

    # Lifecycle
    status: Mapped[LeadStatus] = mapped_column(
        SAEnum(LeadStatus, name="lead_status"), default=LeadStatus.new, nullable=False, index=True
    )
    campaign_status: Mapped[CampaignStatus] = mapped_column(
        SAEnum(CampaignStatus, name="campaign_status"), default=CampaignStatus.none, nullable=False
    )

    notes: Mapped[str | None] = mapped_column(Text)
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    workspace: Mapped["Workspace"] = relationship(back_populates="leads")
    company: Mapped["Company"] = relationship(back_populates="leads")
    source: Mapped["LeadSource"] = relationship(back_populates="leads")
