from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.db.session import get_db
from app.models.campaign import Campaign, CampaignLead, CampaignStep
from app.models.enums import (
    AuditAction,
    CampaignLeadState,
    CampaignState,
    MessageDirection,
    WorkspaceRole,
)
from app.models.lead import Lead
from app.models.message import Message
from app.schemas.campaign import (
    AddLeadsRequest,
    AddLeadsResponse,
    CampaignCreate,
    CampaignLeadOut,
    CampaignOut,
    CampaignStats,
    CampaignUpdate,
    CanSendPreview,
    CanSendResult,
    MessageOut,
    TransitionResponse,
)
from app.services import audit, campaign_service
from app.services.can_send import can_send

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

_EDITABLE_STATES = {CampaignState.draft, CampaignState.scheduled, CampaignState.paused}


def _get_owned(db: Session, ws_id: str, campaign_id: str) -> Campaign:
    c = db.get(Campaign, campaign_id)
    if c is None or c.workspace_id != ws_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    return c


def _stats(db: Session, campaign_id: str) -> CampaignStats:
    rows = db.execute(
        select(CampaignLead.state, func.count()).where(
            CampaignLead.campaign_id == campaign_id
        ).group_by(CampaignLead.state)
    ).all()
    by_state = {state: n for state, n in rows}
    sent = db.execute(
        select(func.count()).select_from(Message).where(
            Message.campaign_id == campaign_id,
            Message.direction == MessageDirection.outbound,
        )
    ).scalar_one()
    return CampaignStats(
        total=sum(by_state.values()),
        pending=by_state.get(CampaignLeadState.pending, 0),
        active=by_state.get(CampaignLeadState.active, 0),
        completed=by_state.get(CampaignLeadState.completed, 0),
        replied=by_state.get(CampaignLeadState.replied, 0),
        skipped=by_state.get(CampaignLeadState.skipped, 0),
        failed=by_state.get(CampaignLeadState.failed, 0),
        awaiting_action=by_state.get(CampaignLeadState.awaiting_action, 0),
        messages_sent=sent,
    )


def _to_out(db: Session, c: Campaign, *, with_stats: bool = True) -> CampaignOut:
    out = CampaignOut.model_validate(c)
    if with_stats:
        out.stats = _stats(db, c.id)
    return out


@router.get("", response_model=list[CampaignOut])
def list_campaigns(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[CampaignOut]:
    rows = db.execute(
        select(Campaign).where(Campaign.workspace_id == ctx.workspace_id)
        .order_by(Campaign.created_at.desc())
    ).scalars().all()
    return [_to_out(db, c) for c in rows]


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> CampaignOut:
    campaign = Campaign(
        workspace_id=ctx.workspace_id,
        created_by=ctx.user.id,
        name=payload.name,
        description=payload.description,
        channels={k: v.model_dump(exclude_none=True) for k, v in payload.channels.items()},
        approval_mode=payload.approval_mode,
        test_mode=payload.test_mode,
        state=CampaignState.draft,
    )
    db.add(campaign)
    db.flush()
    if payload.steps:
        campaign_service.set_steps(db, campaign, [s.model_dump() for s in payload.steps])
    audit.record(db, action=AuditAction.create, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="campaign", entity_id=campaign.id)
    db.commit()
    db.refresh(campaign)
    return _to_out(db, campaign)


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(
    campaign_id: str,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> CampaignOut:
    return _to_out(db, _get_owned(db, ctx.workspace_id, campaign_id))


@router.patch("/{campaign_id}", response_model=CampaignOut)
def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> CampaignOut:
    c = _get_owned(db, ctx.workspace_id, campaign_id)
    if c.state not in _EDITABLE_STATES:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Cannot edit a {c.state.value} campaign")
    data = payload.model_dump(exclude_unset=True)
    if payload.channels is not None:
        c.channels = {k: v.model_dump(exclude_none=True) for k, v in payload.channels.items()}
    for field in ("name", "description", "approval_mode", "test_mode"):
        if field in data and data[field] is not None:
            setattr(c, field, data[field])
    if payload.steps is not None:
        campaign_service.set_steps(db, c, [s.model_dump() for s in payload.steps])
    audit.record(db, action=AuditAction.update, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="campaign", entity_id=c.id)
    db.commit()
    db.refresh(c)
    return _to_out(db, c)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_campaign(
    campaign_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin)),
    db: Session = Depends(get_db),
) -> None:
    c = _get_owned(db, ctx.workspace_id, campaign_id)
    db.delete(c)
    audit.record(db, action=AuditAction.delete, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="campaign", entity_id=campaign_id)
    db.commit()


# ---- Membership ----

@router.get("/{campaign_id}/leads", response_model=list[CampaignLeadOut])
def list_members(
    campaign_id: str,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[CampaignLeadOut]:
    _get_owned(db, ctx.workspace_id, campaign_id)
    rows = db.execute(
        select(CampaignLead, Lead).join(Lead, Lead.id == CampaignLead.lead_id)
        .where(CampaignLead.campaign_id == campaign_id)
        .order_by(CampaignLead.created_at.asc())
    ).all()
    out: list[CampaignLeadOut] = []
    for member, lead in rows:
        item = CampaignLeadOut.model_validate(member)
        item.lead_name = lead.full_name
        item.lead_email = lead.email
        out.append(item)
    return out


@router.post("/{campaign_id}/leads", response_model=AddLeadsResponse)
def add_members(
    campaign_id: str,
    payload: AddLeadsRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> AddLeadsResponse:
    c = _get_owned(db, ctx.workspace_id, campaign_id)
    added = campaign_service.add_leads(db, c, payload.lead_ids)
    db.commit()
    return AddLeadsResponse(added=added)


@router.delete("/{campaign_id}/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def remove_member(
    campaign_id: str,
    lead_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> None:
    c = _get_owned(db, ctx.workspace_id, campaign_id)
    member = db.execute(
        select(CampaignLead).where(
            CampaignLead.campaign_id == c.id, CampaignLead.lead_id == lead_id
        )
    ).scalar_one_or_none()
    if member:
        db.delete(member)
        db.commit()


# ---- State transitions ----

def _enqueue_tick() -> None:
    """Kick the worker to process immediately (best-effort; beat also runs it)."""
    try:
        from app.worker.tasks import run_tick
        run_tick.delay()
    except Exception:  # noqa: BLE001 — broker down shouldn't fail the request; beat will catch up
        pass


@router.post("/{campaign_id}/launch", response_model=TransitionResponse)
def launch_campaign(
    campaign_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> TransitionResponse:
    c = _get_owned(db, ctx.workspace_id, campaign_id)
    campaign_service.launch(db, c)
    audit.record(db, action=AuditAction.campaign_launch, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="campaign", entity_id=c.id)
    db.commit()
    _enqueue_tick()
    return TransitionResponse(id=c.id, state=c.state)


@router.post("/{campaign_id}/pause", response_model=TransitionResponse)
def pause_campaign(
    campaign_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> TransitionResponse:
    c = _get_owned(db, ctx.workspace_id, campaign_id)
    campaign_service.pause(db, c)
    audit.record(db, action=AuditAction.campaign_pause, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="campaign", entity_id=c.id)
    db.commit()
    return TransitionResponse(id=c.id, state=c.state)


@router.post("/{campaign_id}/resume", response_model=TransitionResponse)
def resume_campaign(
    campaign_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> TransitionResponse:
    c = _get_owned(db, ctx.workspace_id, campaign_id)
    campaign_service.resume(db, c)
    audit.record(db, action=AuditAction.campaign_resume, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="campaign", entity_id=c.id)
    db.commit()
    _enqueue_tick()
    return TransitionResponse(id=c.id, state=c.state)


@router.post("/{campaign_id}/complete", response_model=TransitionResponse)
def complete_campaign(
    campaign_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> TransitionResponse:
    c = _get_owned(db, ctx.workspace_id, campaign_id)
    campaign_service.complete(db, c)
    audit.record(db, action=AuditAction.campaign_complete, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="campaign", entity_id=c.id)
    db.commit()
    return TransitionResponse(id=c.id, state=c.state)


# ---- Preview + messages ----

@router.post("/{campaign_id}/preview-send", response_model=CanSendResult)
def preview_send(
    campaign_id: str,
    payload: CanSendPreview,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> CanSendResult:
    c = _get_owned(db, ctx.workspace_id, campaign_id)
    lead = db.get(Lead, payload.lead_id)
    if lead is None or lead.workspace_id != ctx.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    ch = payload.channel.value
    value = {"email": lead.email, "whatsapp": lead.phone, "linkedin": lead.linkedin_url}.get(ch, "")
    decision = can_send(db, campaign=c, channel=ch, lead_value=value or "", lead_id=lead.id)
    return CanSendResult(allowed=decision.allowed, reasons=decision.reasons, checks=decision.checks)


@router.get("/{campaign_id}/messages", response_model=list[MessageOut])
def list_messages(
    campaign_id: str,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    _get_owned(db, ctx.workspace_id, campaign_id)
    rows = db.execute(
        select(Message).where(Message.campaign_id == campaign_id)
        .order_by(Message.created_at.desc()).limit(200)
    ).scalars().all()
    return [MessageOut.model_validate(m) for m in rows]
