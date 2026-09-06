"""Record an inbound WhatsApp message (a reply) received via the service webhook.

Matches the sender's number to a lead (by normalized phone) and to the most recent
outbound WhatsApp message on that number, halts the member's sequence, flips the
lead to `replied`, and runs best-effort AI classification (unsubscribe → suppress
the number). Mirrors the email/LinkedIn reply paths.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.campaign import CampaignLead
from app.models.enums import (
    CampaignLeadState,
    Channel,
    LeadStatus,
    MessageDirection,
    MessageEventType,
    MessageStatus,
    Provenance,
    SuppressionReason,
)
from app.models.lead import Lead
from app.models.message import Message, MessageEvent
from app.services import suppression
from app.utils.normalize import normalize_phone

logger = logging.getLogger(__name__)


def _digits(value: str | None) -> str:
    """Comparable trailing-digit key for a phone / WhatsApp JID ('…@c.us')."""
    norm = normalize_phone((value or "").split("@")[0]) or ""
    return norm.lstrip("+")


def _find_lead_by_phone(db: Session, workspace_id: str, digits: str) -> Lead | None:
    if not digits:
        return None
    # Match on a normalized-digit suffix so stored formats (+1 555…, 1-555…) all resolve.
    return db.execute(
        select(Lead).where(
            Lead.workspace_id == workspace_id,
            Lead.phone.isnot(None),
            func.regexp_replace(Lead.phone, r"\D", "", "g").like(f"%{digits}"),
        ).limit(1)
    ).scalar_one_or_none()


def _latest_outbound_to(db: Session, workspace_id: str, digits: str) -> Message | None:
    if not digits:
        return None
    return db.execute(
        select(Message).where(
            Message.workspace_id == workspace_id,
            Message.direction == MessageDirection.outbound,
            Message.channel == Channel.whatsapp,
            func.regexp_replace(Message.to_address, r"\D", "", "g").like(f"%{digits}"),
        ).order_by(Message.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def record_inbound(db: Session, workspace_id: str, *, from_number: str, body: str,
                   provider_message_id: str | None = None) -> str:
    digits = _digits(from_number)
    origin = _latest_outbound_to(db, workspace_id, digits)
    lead = _find_lead_by_phone(db, workspace_id, digits)
    if lead is None and origin is not None and origin.lead_id:
        lead = db.get(Lead, origin.lead_id)
    if lead is None and origin is None:
        return "reply_unmatched"

    inbound_msg = Message(
        workspace_id=workspace_id,
        lead_id=lead.id if lead else None,
        campaign_id=origin.campaign_id if origin else None,
        campaign_lead_id=origin.campaign_lead_id if origin else None,
        channel=Channel.whatsapp,
        direction=MessageDirection.inbound,
        status=MessageStatus.replied,
        body=body,
        to_address=normalize_phone(from_number.split("@")[0]),
        provider_message_id=provider_message_id,
        meta={"from_address": normalize_phone(from_number.split("@")[0])},
    )
    db.add(inbound_msg)
    db.flush()
    db.add(MessageEvent(
        workspace_id=workspace_id, message_id=(origin.id if origin else inbound_msg.id),
        type=MessageEventType.replied, provenance=Provenance.observed,
        detail={"from": from_number},
    ))

    if origin and origin.campaign_lead_id:
        member = db.get(CampaignLead, origin.campaign_lead_id)
        # A reply supersedes any non-negative state, including a member that already
        # finished a short sequence (single-step campaigns complete on the send).
        if member and member.state in (
            CampaignLeadState.active, CampaignLeadState.pending,
            CampaignLeadState.awaiting_action, CampaignLeadState.completed,
        ):
            member.state = CampaignLeadState.replied
            member.next_action_at = None
            member.last_reason = "replied"
    if lead:
        lead.status = LeadStatus.replied

    _classify_and_annotate(db, workspace_id, inbound_msg, body, lead)
    return "reply_recorded"


def _classify_and_annotate(db: Session, workspace_id: str, inbound_msg: Message,
                           body: str, lead: Lead | None) -> None:
    try:
        from app.services.ai import log as ai_log
        from app.services.ai.factory import get_ai_service

        svc = get_ai_service()
        if not svc.enabled:
            return
        res = svc.classify_reply(body, {"channel": "whatsapp"})
        ai_log.record(db, res, workspace_id=workspace_id, lead_id=inbound_msg.lead_id,
                      message_id=inbound_msg.id)
        if not res.ok:
            return
        intent = res.output.get("intent")
        meta = dict(inbound_msg.meta or {})
        meta["ai_intent"] = intent
        meta["ai_sentiment"] = res.output.get("sentiment")
        inbound_msg.meta = meta
        if intent == "unsubscribe" and inbound_msg.to_address:
            suppression.add_suppression(
                db, workspace_id, "whatsapp", inbound_msg.to_address,
                SuppressionReason.unsubscribed, note="AI-classified unsubscribe (WhatsApp reply)",
            )
    except Exception:  # noqa: BLE001 — classification is best-effort
        logger.warning("WhatsApp reply classification failed", exc_info=True)
