"""Campaign management: create/update, steps, membership, and state transitions.

State machine (enforced here):
    draft ─┬─> active ──> paused ──> active
           └─> scheduled ─> active ──> completed
    (any) ─> archived
No outbound work happens in these calls — launching only seeds member schedules;
the worker's tick() does the sending.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignLead, CampaignStep
from app.models.enums import CampaignLeadState, CampaignState, Channel
from app.models.lead import Lead

_ALLOWED_TRANSITIONS: dict[CampaignState, set[CampaignState]] = {
    CampaignState.draft: {CampaignState.active, CampaignState.scheduled, CampaignState.archived},
    CampaignState.scheduled: {CampaignState.active, CampaignState.paused, CampaignState.archived},
    CampaignState.active: {CampaignState.paused, CampaignState.completed, CampaignState.archived},
    CampaignState.paused: {CampaignState.active, CampaignState.completed, CampaignState.archived},
    CampaignState.completed: {CampaignState.archived},
    CampaignState.archived: set(),
}


def _assert_transition(current: CampaignState, target: CampaignState) -> None:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot move campaign from {current.value} to {target.value}",
        )


def set_steps(db: Session, campaign: Campaign, steps_in: list[dict]) -> None:
    """Replace the campaign's sequence steps (re-indexed by position)."""
    for existing in list(campaign.steps):
        db.delete(existing)
    db.flush()
    for i, s in enumerate(steps_in):
        db.add(CampaignStep(
            campaign_id=campaign.id,
            order_index=i,
            channel=Channel(s["channel"]),
            delay_days=int(s.get("delay_days", 0)),
            subject=s.get("subject"),
            body_template=s.get("body_template"),
            ai_prompt=s.get("ai_prompt"),
            enabled=bool(s.get("enabled", True)),
        ))
    db.flush()


def add_leads(db: Session, campaign: Campaign, lead_ids: list[str]) -> int:
    """Add leads as pending members (idempotent; workspace-scoped)."""
    existing = set(db.execute(
        select(CampaignLead.lead_id).where(CampaignLead.campaign_id == campaign.id)
    ).scalars().all())

    valid = db.execute(
        select(Lead.id).where(Lead.workspace_id == campaign.workspace_id, Lead.id.in_(lead_ids))
    ).scalars().all()

    added = 0
    for lid in valid:
        if lid in existing:
            continue
        db.add(CampaignLead(
            campaign_id=campaign.id,
            lead_id=lid,
            workspace_id=campaign.workspace_id,
            state=CampaignLeadState.pending,
        ))
        added += 1
    db.flush()
    return added


def _enabled_steps(campaign: Campaign) -> list[CampaignStep]:
    return [s for s in sorted(campaign.steps, key=lambda x: x.order_index) if s.enabled]


def launch(db: Session, campaign: Campaign, *, now: datetime | None = None) -> Campaign:
    """Move a draft/scheduled campaign to active and seed member schedules."""
    now = now or datetime.now(timezone.utc)
    if campaign.state not in (CampaignState.draft, CampaignState.scheduled):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only a draft or scheduled campaign can be launched (is {campaign.state.value})",
        )
    steps = _enabled_steps(campaign)
    if not steps:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Campaign has no enabled steps")
    if not any((campaign.channels or {}).get(s.channel.value, {}).get("enabled") for s in steps):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No channel used by the sequence is enabled on the campaign")

    members = db.execute(
        select(CampaignLead).where(
            CampaignLead.campaign_id == campaign.id,
            CampaignLead.state == CampaignLeadState.pending,
        )
    ).scalars().all()
    if not members and not db.execute(
        select(CampaignLead.id).where(CampaignLead.campaign_id == campaign.id).limit(1)
    ).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Campaign has no leads")

    _assert_transition(campaign.state, CampaignState.active)
    first_delay = steps[0].delay_days
    for m in members:
        m.state = CampaignLeadState.active
        m.current_step = 0
        m.attempts = 0
        m.next_action_at = now + timedelta(days=first_delay)

    campaign.state = CampaignState.active
    campaign.started_at = campaign.started_at or now
    db.flush()
    return campaign


def pause(db: Session, campaign: Campaign) -> Campaign:
    _assert_transition(campaign.state, CampaignState.paused)
    campaign.state = CampaignState.paused
    db.flush()
    return campaign


def resume(db: Session, campaign: Campaign) -> Campaign:
    if campaign.state != CampaignState.paused:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only a paused campaign can be resumed (is {campaign.state.value})",
        )
    campaign.state = CampaignState.active
    db.flush()
    return campaign


def complete(db: Session, campaign: Campaign, *, now: datetime | None = None) -> Campaign:
    _assert_transition(campaign.state, CampaignState.completed)
    campaign.state = CampaignState.completed
    campaign.completed_at = now or datetime.now(timezone.utc)
    db.flush()
    return campaign
