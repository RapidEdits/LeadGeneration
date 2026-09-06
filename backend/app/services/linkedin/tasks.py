"""The assisted-LinkedIn task queue: list open tasks, confirm a manual send,
skip a task, and log a manually-received reply.

Every mutation is workspace-scoped and validated against the owning campaign. The
completion/skip paths delegate sequence advancement to ``engine.advance_member`` so
a human-confirmed send moves the member through the sequence exactly like an
automated one; the reply path mirrors ``inbound.record_reply`` (halt member, mark
lead replied, best-effort AI classification with unsubscribe → suppression).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignLead
from app.models.enums import (
    AuditAction,
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
from app.services import audit, engine, suppression

logger = logging.getLogger(__name__)


class TaskNotFound(RuntimeError):
    pass


class TaskNotOpen(RuntimeError):
    pass


@dataclass
class LinkedInTask:
    message: Message
    lead: Lead | None
    campaign: Campaign | None


def list_tasks(db: Session, workspace_id: str, *, limit: int = 200) -> list[LinkedInTask]:
    """Open assisted-LinkedIn tasks for a workspace, oldest first (work them in order)."""
    rows = db.execute(
        select(Message, Lead, Campaign)
        .join(Lead, Lead.id == Message.lead_id, isouter=True)
        .join(Campaign, Campaign.id == Message.campaign_id, isouter=True)
        .where(
            Message.workspace_id == workspace_id,
            Message.channel == Channel.linkedin,
            Message.direction == MessageDirection.outbound,
            Message.status == MessageStatus.pending_action,
        )
        .order_by(Message.created_at.asc())
        .limit(limit)
    ).all()
    return [LinkedInTask(message=m, lead=lead, campaign=camp) for m, lead, camp in rows]


def _get_open_task(db: Session, workspace_id: str, message_id: str) -> Message:
    msg = db.get(Message, message_id)
    if (
        msg is None
        or msg.workspace_id != workspace_id
        or msg.channel != Channel.linkedin
        or msg.direction != MessageDirection.outbound
    ):
        raise TaskNotFound("LinkedIn task not found")
    if msg.status != MessageStatus.pending_action:
        raise TaskNotOpen("This task is no longer open")
    return msg


def complete_task(
    db: Session, workspace_id: str, message_id: str, *, actor_id: str | None = None, note: str | None = None
) -> Message:
    """Operator confirms they sent the message on LinkedIn. Mark it sent + advance."""
    msg = _get_open_task(db, workspace_id, message_id)
    now = datetime.now(timezone.utc)
    msg.status = MessageStatus.sent
    if not msg.provider_message_id:
        msg.provider_message_id = f"li_manual_{uuid.uuid4().hex[:16]}"
    meta = dict(msg.meta or {})
    if note:
        meta["operator_note"] = note
    meta["confirmed_by"] = actor_id
    msg.meta = meta
    db.add(MessageEvent(
        workspace_id=workspace_id, message_id=msg.id, type=MessageEventType.sent,
        provenance=Provenance.observed, detail={"assisted": True, "confirmed_by": actor_id},
    ))

    if msg.campaign_lead_id:
        member = db.get(CampaignLead, msg.campaign_lead_id)
        campaign = db.get(Campaign, msg.campaign_id) if msg.campaign_id else None
        if member and campaign:
            engine.advance_member(db, campaign, member, now)

    audit.record(db, action=AuditAction.message_sent, workspace_id=workspace_id,
                 actor_id=actor_id, entity_type="message", entity_id=msg.id,
                 data={"channel": "linkedin", "assisted": True})
    db.commit()
    db.refresh(msg)
    return msg


def skip_task(
    db: Session, workspace_id: str, message_id: str, *, actor_id: str | None = None, reason: str | None = None
) -> Message:
    """Operator declines to send (e.g. profile gone). Mark failed + move past the step."""
    msg = _get_open_task(db, workspace_id, message_id)
    now = datetime.now(timezone.utc)
    msg.status = MessageStatus.failed
    meta = dict(msg.meta or {})
    meta["skip_reason"] = reason or "skipped_by_operator"
    msg.meta = meta
    db.add(MessageEvent(
        workspace_id=workspace_id, message_id=msg.id, type=MessageEventType.failed,
        provenance=Provenance.observed, detail={"assisted": True, "skipped": True, "reason": reason},
    ))
    if msg.campaign_lead_id:
        member = db.get(CampaignLead, msg.campaign_lead_id)
        campaign = db.get(Campaign, msg.campaign_id) if msg.campaign_id else None
        if member and campaign:
            engine.advance_member(db, campaign, member, now)
    audit.record(db, action=AuditAction.send_blocked, workspace_id=workspace_id,
                 actor_id=actor_id, entity_type="message", entity_id=msg.id,
                 data={"channel": "linkedin", "skipped": True, "reason": reason})
    db.commit()
    db.refresh(msg)
    return msg


def log_reply(
    db: Session, workspace_id: str, message_id: str, *, text: str,
    from_name: str | None = None, actor_id: str | None = None,
) -> Message:
    """Record a reply the operator received on LinkedIn against the sent task's thread.

    Halts the member's sequence, flips the lead to `replied`, and runs best-effort AI
    classification (an `unsubscribe` intent suppresses the lead's LinkedIn URL)."""
    origin = db.get(Message, message_id)
    if origin is None or origin.workspace_id != workspace_id or origin.channel != Channel.linkedin:
        raise TaskNotFound("LinkedIn message not found")

    lead = db.get(Lead, origin.lead_id) if origin.lead_id else None
    inbound_msg = Message(
        workspace_id=workspace_id,
        lead_id=origin.lead_id,
        campaign_id=origin.campaign_id,
        campaign_lead_id=origin.campaign_lead_id,
        channel=Channel.linkedin,
        direction=MessageDirection.inbound,
        status=MessageStatus.replied,
        body=text,
        to_address=lead.linkedin_url if lead else None,
        meta={"from_name": from_name, "from_address": from_name, "logged_by": actor_id},
    )
    db.add(inbound_msg)
    db.flush()
    db.add(MessageEvent(
        workspace_id=workspace_id, message_id=origin.id, type=MessageEventType.replied,
        provenance=Provenance.observed, detail={"assisted": True, "from_name": from_name},
    ))

    if origin.campaign_lead_id:
        from app.models.enums import CampaignLeadState
        member = db.get(CampaignLead, origin.campaign_lead_id)
        # A logged reply supersedes any non-terminal-negative state — including a
        # member that already finished the sequence (single-step LinkedIn campaigns
        # complete on the send confirmation, and a later reply still matters).
        if member and member.state in (
            CampaignLeadState.active, CampaignLeadState.pending,
            CampaignLeadState.awaiting_action, CampaignLeadState.completed,
        ):
            member.state = CampaignLeadState.replied
            member.next_action_at = None
            member.last_reason = "replied"
    if lead:
        lead.status = LeadStatus.replied

    _classify_and_annotate(db, workspace_id, inbound_msg, text, lead)
    db.commit()
    db.refresh(inbound_msg)
    return inbound_msg


def _classify_and_annotate(
    db: Session, workspace_id: str, inbound_msg: Message, text: str, lead: Lead | None
) -> None:
    """Best-effort AI classification of a LinkedIn reply. Never raises."""
    try:
        from app.services.ai import log as ai_log
        from app.services.ai.factory import get_ai_service

        svc = get_ai_service()
        if not svc.enabled:
            return
        res = svc.classify_reply(text, {"channel": "linkedin"})
        ai_log.record(db, res, workspace_id=workspace_id, lead_id=inbound_msg.lead_id,
                      message_id=inbound_msg.id)
        if not res.ok:
            return
        intent = res.output.get("intent")
        meta = dict(inbound_msg.meta or {})
        meta["ai_intent"] = intent
        meta["ai_sentiment"] = res.output.get("sentiment")
        inbound_msg.meta = meta
        if intent == "unsubscribe" and lead and lead.linkedin_url:
            suppression.add_suppression(
                db, workspace_id, "linkedin", lead.linkedin_url,
                SuppressionReason.unsubscribed, note="AI-classified unsubscribe (LinkedIn reply)",
            )
    except Exception:  # noqa: BLE001 — classification is best-effort
        logger.warning("LinkedIn reply classification failed", exc_info=True)
