"""Campaign execution engine — advances one member through the sequence.

Pure of Celery: the worker task calls `tick()` / `process_member()`, but so do
the unit tests. Every outbound attempt passes through `can_send`; the actual
send goes through a ChannelProvider (SimulatedProvider in test mode).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignLead, CampaignStep
from app.models.enums import (
    AuditAction,
    CampaignLeadState,
    CampaignState,
    Channel,
    MessageDirection,
    MessageEventType,
    MessageStatus,
    Provenance,
    SuppressionReason,
)
from app.models.lead import Lead
from app.models.message import Message, MessageEvent, tracking_token
from app.services import audit, suppression
from app.services.can_send import can_send
from app.services.channel_provider import OutboundMessage, get_provider

logger = logging.getLogger(__name__)

# Transient block reasons → reschedule and retry later. Others are terminal.
_TRANSIENT = {"account_connected", "frequency_ok", "rate_limit_ok", "schedule_ok", "approval_satisfied"}
RETRY_BACKOFF = timedelta(hours=1)
MAX_ATTEMPTS = 24  # ~1 day of hourly retries before giving up


def render_template(text: str | None, lead: Lead) -> str:
    if not text:
        return ""
    values = {
        "first_name": lead.first_name or (lead.full_name.split(" ")[0] if lead.full_name else "there"),
        "last_name": lead.last_name or "",
        "full_name": lead.full_name or "there",
        "title": lead.title or "",
        "email": lead.email or "",
        "location": lead.location or "",
    }
    return re.sub(
        r"\{\{\s*(\w+)\s*\}\}",
        lambda m: str(values.get(m.group(1), m.group(0))),
        text,
    )


def _lead_value(lead: Lead, channel: str) -> str:
    if channel == Channel.email.value:
        return lead.email or ""
    if channel == Channel.whatsapp.value:
        return lead.phone or ""
    if channel == Channel.linkedin.value:
        return lead.linkedin_url or ""
    return ""


def _enabled_steps(campaign: Campaign) -> list[CampaignStep]:
    return [s for s in sorted(campaign.steps, key=lambda x: x.order_index) if s.enabled]


def _schedule_next(member: CampaignLead, steps: list[CampaignStep], from_time: datetime) -> None:
    """Point member at its next step, or complete it if none remain."""
    if member.current_step >= len(steps):
        member.state = CampaignLeadState.completed
        member.next_action_at = None
        return
    step = steps[member.current_step]
    member.next_action_at = from_time + timedelta(days=step.delay_days)


def advance_member(db: Session, campaign: Campaign, member: CampaignLead, now: datetime | None = None) -> None:
    """Mark the current step done and schedule the next one (or complete the member).

    Shared by the in-engine send-success path and the assisted-task completion flow
    (LinkedIn), so a manually-confirmed send advances the sequence identically."""
    now = now or datetime.now(timezone.utc)
    member.state = CampaignLeadState.active
    member.last_sent_at = now
    member.attempts = 0
    member.last_reason = None
    member.current_step += 1
    _schedule_next(member, _enabled_steps(campaign), now)


def process_member(db: Session, member: CampaignLead, now: datetime | None = None) -> str:
    """Process one due member. Returns a short outcome string for logging/metrics."""
    now = now or datetime.now(timezone.utc)
    campaign = db.get(Campaign, member.campaign_id)
    if not campaign or campaign.state != CampaignState.active:
        return "campaign_inactive"

    steps = _enabled_steps(campaign)
    if member.state != CampaignLeadState.active:
        return f"member_{member.state.value}"

    if member.current_step >= len(steps):
        member.state = CampaignLeadState.completed
        member.next_action_at = None
        return "completed"

    step = steps[member.current_step]
    lead = db.get(Lead, member.lead_id)
    if not lead:
        member.state = CampaignLeadState.failed
        member.next_action_at = None
        return "lead_missing"

    channel = step.channel.value
    value = _lead_value(lead, channel)

    decision = can_send(
        db, campaign=campaign, channel=channel, lead_value=value, lead_id=lead.id, now=now
    )

    if not decision.allowed:
        member.last_reason = decision.reasons[0] if decision.reasons else "blocked"
        # Terminal: channel disabled for this step → skip just this step.
        if not decision.checks.get("channel_enabled", True):
            member.current_step += 1
            _schedule_next(member, steps, now)
            return "step_skipped_channel_disabled"
        # Terminal: suppressed → stop contacting this lead entirely.
        if not decision.checks.get("not_suppressed", True):
            member.state = CampaignLeadState.skipped
            member.next_action_at = None
            _record_blocked(db, campaign, member, lead, channel, "suppressed")
            return "skipped_suppressed"
        # Transient → back off and retry, up to a cap.
        if any(r in _TRANSIENT for r in decision.reasons):
            # Waiting for a daily budget or sending window is normal bulk scheduling,
            # not a failed provider attempt. Large batches may legitimately span days.
            if set(decision.reasons) <= {"frequency_ok", "rate_limit_ok", "schedule_ok"}:
                member.next_action_at = now + RETRY_BACKOFF
                return f"deferred_{member.last_reason}"
            member.attempts += 1
            if member.attempts >= MAX_ATTEMPTS:
                member.state = CampaignLeadState.failed
                member.next_action_at = None
                return "failed_max_attempts"
            member.next_action_at = now + RETRY_BACKOFF
            return f"deferred_{member.last_reason}"
        # Any other denial is terminal.
        member.state = CampaignLeadState.skipped
        member.next_action_at = None
        _record_blocked(db, campaign, member, lead, channel, member.last_reason)
        return f"skipped_{member.last_reason}"

    # Allowed → render, persist a queued Message (so tracking binds to it), then dispatch.
    subject = render_template(step.subject, lead) if step.subject else None
    body = render_template(step.body_template, lead)

    # AI personalization: when the step carries an ai_prompt, ask the AIService for a
    # tailored body. Any "unknown"/error result falls back to the rendered template — the
    # sequence never blocks on the model being unavailable.
    ai_result = None
    if step.ai_prompt:
        subject, body, ai_result = _ai_personalize(db, campaign, step, lead, channel, subject, body)

    message = Message(
        workspace_id=campaign.workspace_id,
        lead_id=lead.id,
        campaign_id=campaign.id,
        campaign_lead_id=member.id,
        step_id=step.id,
        channel=Channel(channel),
        direction=MessageDirection.outbound,
        status=MessageStatus.queued,
        subject=subject,
        body=body,
        to_address=value,
        tracking_id=tracking_token(),
        meta={"test_mode": campaign.test_mode},
    )
    db.add(message)
    db.flush()  # assigns id + tracking_id before send

    if ai_result is not None:
        from app.services.ai import log as ai_log
        ai_log.record(db, ai_result, workspace_id=campaign.workspace_id,
                      lead_id=lead.id, campaign_id=campaign.id, message_id=message.id)

    # Assisted-workflow channels (LinkedIn) don't send over the wire. A live send is
    # queued as a manual task for a human operator to action on the platform, then
    # confirmed in-app. Park the member so the scheduler stops reprocessing it; the
    # task-completion endpoint advances the sequence once the operator marks it sent.
    # (Test mode still simulates through the generic provider path below.)
    if channel == Channel.linkedin.value and not campaign.test_mode:
        message.status = MessageStatus.pending_action
        db.add(MessageEvent(
            workspace_id=campaign.workspace_id, message_id=message.id,
            type=MessageEventType.queued, provenance=Provenance.observed,
            detail={"assisted": True, "channel": channel},
        ))
        member.state = CampaignLeadState.awaiting_action
        member.next_action_at = None
        member.last_reason = "awaiting_action"
        return "queued_for_action"

    status, success, provider_message_id, error, hard_bounce = _dispatch(db, campaign, message, channel)
    message.status = status
    message.provider_message_id = provider_message_id

    event_type = (
        MessageEventType.sent if success
        else MessageEventType.bounced if hard_bounce
        else MessageEventType.failed
    )
    db.add(MessageEvent(
        workspace_id=campaign.workspace_id,
        message_id=message.id,
        type=event_type,
        provenance=Provenance.estimated if campaign.test_mode else Provenance.observed,
        detail={"simulated": campaign.test_mode, "error": error},
    ))

    if not success:
        if hard_bounce:
            # Hard bounce at send time → suppress the address and stop this lead's sequence.
            suppression.add_suppression(
                db, campaign.workspace_id, channel, value,
                SuppressionReason.bounced, note="Hard bounce at send time",
            )
            member.state = CampaignLeadState.bounced
            member.next_action_at = None
            member.last_reason = "bounced"
            return "bounced"
        member.attempts += 1
        if member.attempts >= MAX_ATTEMPTS:
            member.state = CampaignLeadState.failed
            member.next_action_at = None
            member.last_reason = "send_failed"
            return "failed_max_attempts"
        member.next_action_at = now + RETRY_BACKOFF
        member.last_reason = "send_failed"
        return "send_failed"

    member.last_sent_at = now
    member.attempts = 0
    member.current_step += 1
    _schedule_next(member, steps, now)
    audit.record(db, action=AuditAction.message_sent, workspace_id=campaign.workspace_id,
                 entity_type="message", entity_id=message.id,
                 data={"campaign_id": campaign.id, "channel": channel, "test_mode": campaign.test_mode})
    return "sent"


def _ai_personalize(db, campaign, step, lead, channel, subject, body):
    """Attempt AI personalization for a step. Returns (subject, body, ai_result).
    Falls back to the template values on any non-ok result — never raises."""
    from app.models.lead import Company
    from app.services.ai.factory import get_ai_service

    svc = get_ai_service()
    lead_facts = {
        "full_name": lead.full_name, "first_name": lead.first_name, "title": lead.title,
        "email": lead.email, "location": lead.location, "linkedin_url": lead.linkedin_url,
    }
    if lead.company_id:
        company = db.get(Company, lead.company_id)
        if company:
            lead_facts.update({"company_name": company.name, "industry": company.industry})
    context = {"instructions": step.ai_prompt, "campaign": campaign.name,
               "template_subject": subject, "template_body": body}
    try:
        if channel == Channel.linkedin.value:
            res = svc.generate_linkedin_message(lead_facts, context)
        else:
            res = svc.generate_email(lead_facts, context)
    except Exception as exc:  # noqa: BLE001 — never let personalization block a send
        logger.warning("AI personalization failed: %s", exc)
        return subject, body, None
    if res.ok:
        new_body = res.output.get("body")
        if new_body:
            body = new_body
        new_subject = res.output.get("subject")
        if new_subject and channel == Channel.email.value:
            subject = new_subject
    return subject, body, res


def _dispatch(
    db: Session, campaign: Campaign, message: Message, channel: str
) -> tuple[MessageStatus, bool, str | None, str | None, bool]:
    """Send `message` via the right provider. Returns
    (status, success, provider_message_id, error, hard_bounce)."""
    # Live email goes through the real EmailProvider stack (Gmail/Microsoft/SMTP).
    if channel == Channel.email.value and not campaign.test_mode:
        from app.services.email import sender as email_sender
        from app.services.email.factory import NoEmailAccount
        try:
            r = email_sender.send_campaign_message(db, message)
        except NoEmailAccount as exc:  # account disconnected between gate and send → retry
            return MessageStatus.failed, False, None, str(exc), False
        if r.success:
            return MessageStatus.sent, True, r.provider_message_id, None, False
        return (
            MessageStatus.bounced if r.hard_bounce else MessageStatus.failed,
            False, r.provider_message_id, r.error, r.hard_bounce,
        )

    # Generic path: SimulatedProvider (test mode) or NotImplementedProvider (other channels).
    provider = get_provider(channel, test_mode=campaign.test_mode)
    r = provider.send(OutboundMessage(
        channel=channel, to_address=message.to_address, subject=message.subject, body=message.body
    ))
    return r.status, r.success, r.provider_message_id, r.error, False


def _record_blocked(db, campaign, member, lead, channel, reason) -> None:
    audit.record(db, action=AuditAction.send_blocked, workspace_id=campaign.workspace_id,
                 entity_type="campaign_lead", entity_id=member.id,
                 data={"reason": reason, "channel": channel, "lead_id": lead.id})


def tick(db: Session, now: datetime | None = None, limit: int = 200) -> dict:
    """Process all members that are due. Returns a small outcome histogram."""
    now = now or datetime.now(timezone.utc)
    active_campaign_ids = db.execute(
        # ponytail: lock the selected campaigns for this tick; partition batches if
        # throughput later requires it. Concurrent beat/on-demand ticks skip them.
        select(Campaign.id).where(Campaign.state == CampaignState.active).with_for_update(skip_locked=True)
    ).scalars().all()
    if not active_campaign_ids:
        return {}

    due = db.execute(
        select(CampaignLead).where(
            CampaignLead.campaign_id.in_(active_campaign_ids),
            CampaignLead.state == CampaignLeadState.active,
            CampaignLead.next_action_at.isnot(None),
            CampaignLead.next_action_at <= now,
        ).limit(limit)
    ).scalars().all()

    outcomes: dict[str, int] = {}
    for member in due:
        outcome = process_member(db, member, now)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1

    # Auto-complete campaigns whose members are all finished.
    for cid in active_campaign_ids:
        remaining = db.execute(
            select(CampaignLead.id).where(
                CampaignLead.campaign_id == cid,
                CampaignLead.state.in_([
                    CampaignLeadState.active,
                    CampaignLeadState.pending,
                    # Open assisted (LinkedIn) tasks keep the campaign live until worked.
                    CampaignLeadState.awaiting_action,
                ]),
            ).limit(1)
        ).first()
        if remaining is None:
            camp = db.get(Campaign, cid)
            if camp and camp.state == CampaignState.active:
                camp.state = CampaignState.completed
                camp.completed_at = now

    db.commit()
    return outcomes
