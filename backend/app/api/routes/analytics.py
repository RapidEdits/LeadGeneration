"""Analytics endpoints (Phase 8): workspace-level reporting — overview KPIs, the
lead funnel, outreach performance by channel, a daily activity time series,
per-campaign performance, and AI-generated insights.

Everything is workspace-scoped and read-only (viewer role is enough), except the
AI insights call which writes an AIGeneration audit row (sales role, same as the
rest of /ai).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.db.session import get_db
from app.models.campaign import Campaign, CampaignLead
from app.models.crm import Task
from app.models.enums import (
    CampaignLeadState,
    CampaignState,
    LeadStatus,
    MessageDirection,
    MessageEventType,
    MessageStatus,
    TaskStatus,
    WorkspaceRole,
)
from app.models.lead import Lead
from app.models.message import Message, MessageEvent
from app.schemas.analytics import (
    CampaignPerformance,
    CampaignsPerformanceResponse,
    ChannelBreakdown,
    FunnelResponse,
    FunnelStage,
    InsightsResponse,
    OutreachResponse,
    OverviewResponse,
    TimeseriesPoint,
    TimeseriesResponse,
)
from app.schemas.ai import AIResultOut
from app.services.ai import log as ai_log
from app.services.ai.factory import get_ai_service
from app.services.message_metrics import accepted_message, real_message

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Linear lead lifecycle used for the funnel (off-ramps lost/disqualified sit outside it).
_FUNNEL: list[tuple[LeadStatus, str]] = [
    (LeadStatus.new, "All leads"),
    (LeadStatus.enriched, "Enriched"),
    (LeadStatus.qualified, "Qualified"),
    (LeadStatus.contacted, "Contacted"),
    (LeadStatus.replied, "Replied"),
    (LeadStatus.won, "Won"),
]
_RANK = {st: i for i, (st, _) in enumerate(_FUNNEL)}


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _window(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _count(db: Session, model, *conds) -> int:
    return db.execute(select(func.count()).select_from(model).where(*conds)).scalar_one()


# ---------------------------------------------------------------------------

@router.get("/overview", response_model=OverviewResponse)
def overview(
    days: int = Query(30, ge=1, le=365),
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> OverviewResponse:
    ws = ctx.workspace_id
    since = _window(days)
    now = datetime.now(timezone.utc)

    by_status = dict(db.execute(
        select(Lead.status, func.count()).where(Lead.workspace_id == ws).group_by(Lead.status)
    ).all())

    messages_sent = _count(
        db, Message, Message.workspace_id == ws,
        Message.direction == MessageDirection.outbound, Message.created_at >= since,
        accepted_message(),
    )
    replies = _count(
        db, Message, Message.workspace_id == ws,
        Message.direction == MessageDirection.inbound, Message.created_at >= since,
    )
    won = by_status.get(LeadStatus.won, 0)
    lost = by_status.get(LeadStatus.lost, 0)

    return OverviewResponse(
        days=days,
        total_leads=sum(by_status.values()),
        new_leads=_count(db, Lead, Lead.workspace_id == ws, Lead.created_at >= since),
        qualified_leads=by_status.get(LeadStatus.qualified, 0),
        contacted_leads=by_status.get(LeadStatus.contacted, 0),
        replied_leads=by_status.get(LeadStatus.replied, 0),
        won_leads=won,
        lost_leads=lost,
        active_campaigns=_count(
            db, Campaign, Campaign.workspace_id == ws, Campaign.state == CampaignState.active
        ),
        messages_sent=messages_sent,
        replies_received=replies,
        reply_rate=_rate(replies, messages_sent),
        win_rate=_rate(won, won + lost),
        open_tasks=_count(db, Task, Task.workspace_id == ws, Task.status == TaskStatus.open),
        overdue_tasks=_count(
            db, Task, Task.workspace_id == ws, Task.status == TaskStatus.open,
            Task.due_at.isnot(None), Task.due_at < now,
        ),
    )


@router.get("/funnel", response_model=FunnelResponse)
def funnel(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> FunnelResponse:
    by_status = dict(db.execute(
        select(Lead.status, func.count())
        .where(Lead.workspace_id == ctx.workspace_id).group_by(Lead.status)
    ).all())
    # A lead "reached" every stage at or below its current rank. Off-ramp leads
    # (lost/disqualified) count only toward the top-of-funnel total.
    reached: list[int] = [0] * len(_FUNNEL)
    for st, n in by_status.items():
        rank = _RANK.get(st)
        if rank is None:  # lost / disqualified
            reached[0] += n
            continue
        for i in range(rank + 1):
            reached[i] += n

    top = reached[0] or 0
    return FunnelResponse(stages=[
        FunnelStage(
            status=st.value, label=label, count=reached[i],
            conversion_from_top=_rate(reached[i], top),
        )
        for i, (st, label) in enumerate(_FUNNEL)
    ])


def _event_counts(db: Session, ws: str, since: datetime, *, per_channel: bool):
    """distinct message_id counts per MessageEvent type, optionally grouped by channel."""
    j = select(MessageEvent.type, func.count(func.distinct(MessageEvent.message_id)))
    if per_channel:
        j = select(
            Message.channel, MessageEvent.type,
            func.count(func.distinct(MessageEvent.message_id)),
        )
    j = j.join(Message, Message.id == MessageEvent.message_id).where(
        MessageEvent.workspace_id == ws, Message.workspace_id == ws, MessageEvent.created_at >= since,
        real_message(),
    )
    j = j.group_by(Message.channel, MessageEvent.type) if per_channel else j.group_by(MessageEvent.type)
    return db.execute(j).all()


@router.get("/outreach", response_model=OutreachResponse)
def outreach(
    days: int = Query(30, ge=1, le=365),
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> OutreachResponse:
    ws = ctx.workspace_id
    since = _window(days)

    # Sent, per channel, from the messages themselves (authoritative).
    sent_rows = dict(db.execute(
        select(Message.channel, func.count()).where(
            Message.workspace_id == ws, Message.direction == MessageDirection.outbound,
            Message.created_at >= since,
            accepted_message(),
        ).group_by(Message.channel)
    ).all())

    # Replies = inbound messages, per channel.
    reply_rows = dict(db.execute(
        select(Message.channel, func.count()).where(
            Message.workspace_id == ws, Message.direction == MessageDirection.inbound,
            Message.created_at >= since,
        ).group_by(Message.channel)
    ).all())

    # Opens / clicks / bounces from normalized events (distinct messages).
    ev: dict[tuple, int] = {(ch, t): n for ch, t, n in _event_counts(db, ws, since, per_channel=True)}

    def evc(channel, *types) -> int:
        return sum(ev.get((channel, t), 0) for t in types)

    channels = sorted(
        {c for c in sent_rows} | {c for c in reply_rows} | {ch for ch, _ in ev},
        key=lambda c: c.value,
    )
    breakdown: list[ChannelBreakdown] = []
    for ch in channels:
        s = sent_rows.get(ch, 0)
        opened = evc(ch, MessageEventType.opened)
        clicked = evc(ch, MessageEventType.clicked)
        replied = reply_rows.get(ch, 0)
        bounced = evc(ch, MessageEventType.bounced)
        breakdown.append(ChannelBreakdown(
            channel=ch.value, sent=s, opened=opened, clicked=clicked,
            replied=replied, bounced=bounced,
            open_rate=_rate(opened, s), reply_rate=_rate(replied, s),
            bounce_rate=_rate(bounced, s),
        ))

    total_sent = sum(sent_rows.values())
    total_opened = sum(b.opened for b in breakdown)
    total_clicked = sum(b.clicked for b in breakdown)
    total_replied = sum(reply_rows.values())
    total_bounced = sum(b.bounced for b in breakdown)
    return OutreachResponse(
        days=days, total_sent=total_sent, total_opened=total_opened,
        total_clicked=total_clicked, total_replied=total_replied, total_bounced=total_bounced,
        open_rate=_rate(total_opened, total_sent), click_rate=_rate(total_clicked, total_sent),
        reply_rate=_rate(total_replied, total_sent), bounce_rate=_rate(total_bounced, total_sent),
        by_channel=breakdown,
    )


@router.get("/timeseries", response_model=TimeseriesResponse)
def timeseries(
    days: int = Query(30, ge=1, le=180),
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> TimeseriesResponse:
    ws = ctx.workspace_id
    start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    d = cast(Lead.created_at, Date)
    leads_by_day = dict(db.execute(
        select(d, func.count()).where(Lead.workspace_id == ws, Lead.created_at >= start).group_by(d)
    ).all())

    md = cast(Message.created_at, Date)
    sent_by_day = dict(db.execute(
        select(md, func.count()).where(
            Message.workspace_id == ws, Message.direction == MessageDirection.outbound,
            Message.created_at >= start,
            accepted_message(),
        ).group_by(md)
    ).all())
    reply_by_day = dict(db.execute(
        select(md, func.count()).where(
            Message.workspace_id == ws, Message.direction == MessageDirection.inbound,
            Message.created_at >= start,
        ).group_by(md)
    ).all())

    points: list[TimeseriesPoint] = []
    for i in range(days):
        day = (start + timedelta(days=i)).date()
        points.append(TimeseriesPoint(
            date=day,
            leads_created=leads_by_day.get(day, 0),
            messages_sent=sent_by_day.get(day, 0),
            replies=reply_by_day.get(day, 0),
        ))
    return TimeseriesResponse(days=days, points=points)


@router.get("/campaigns", response_model=CampaignsPerformanceResponse)
def campaigns_performance(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> CampaignsPerformanceResponse:
    ws = ctx.workspace_id
    campaigns = db.execute(
        select(Campaign).where(Campaign.workspace_id == ws).order_by(Campaign.created_at.desc())
    ).scalars().all()
    if not campaigns:
        return CampaignsPerformanceResponse(campaigns=[])

    ids = [c.id for c in campaigns]
    members = dict(db.execute(
        select(CampaignLead.campaign_id, func.count())
        .where(CampaignLead.campaign_id.in_(ids)).group_by(CampaignLead.campaign_id)
    ).all())
    sent = dict(db.execute(
        select(Message.campaign_id, func.count()).where(
            Message.campaign_id.in_(ids), Message.direction == MessageDirection.outbound,
            accepted_message(),
        ).group_by(Message.campaign_id)
    ).all())
    inbound = dict(db.execute(
        select(Message.campaign_id, func.count()).where(
            Message.campaign_id.in_(ids), Message.direction == MessageDirection.inbound
        ).group_by(Message.campaign_id)
    ).all())
    opened = dict(db.execute(
        select(Message.campaign_id, func.count(func.distinct(MessageEvent.message_id)))
        .join(Message, Message.id == MessageEvent.message_id)
        .where(Message.campaign_id.in_(ids), MessageEvent.type == MessageEventType.opened, real_message())
        .group_by(Message.campaign_id)
    ).all())
    bounced = dict(db.execute(
        select(Message.campaign_id, func.count()).where(
            Message.campaign_id.in_(ids), Message.status == MessageStatus.bounced
        ).group_by(Message.campaign_id)
    ).all())

    rows: list[CampaignPerformance] = []
    for c in campaigns:
        s = sent.get(c.id, 0)
        rep = inbound.get(c.id, 0)
        op = opened.get(c.id, 0)
        bo = bounced.get(c.id, 0)
        rows.append(CampaignPerformance(
            id=c.id, name=c.name, state=c.state.value,
            total_leads=members.get(c.id, 0), messages_sent=s, opened=op, replied=rep, bounced=bo,
            reply_rate=_rate(rep, s), open_rate=_rate(op, s), bounce_rate=_rate(bo, s),
        ))
    return CampaignsPerformanceResponse(campaigns=rows)


@router.post("/insights", response_model=InsightsResponse)
def insights(
    days: int = Query(30, ge=1, le=365),
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> InsightsResponse:
    """Feed the workspace's aggregate outreach + funnel numbers to the AI seam and
    return its summary / strengths / issues / recommendations. Degrades to
    status='unknown' when AI is not configured (never fabricates)."""
    ov = overview(days=days, ctx=ctx, db=db)
    fn = funnel(ctx=ctx, db=db)
    outr = outreach(days=days, ctx=ctx, db=db)

    stats = {
        "window_days": days,
        "total_leads": ov.total_leads,
        "new_leads": ov.new_leads,
        "qualified_leads": ov.qualified_leads,
        "won_leads": ov.won_leads,
        "lost_leads": ov.lost_leads,
        "win_rate": ov.win_rate,
        "active_campaigns": ov.active_campaigns,
        "messages_sent": outr.total_sent,
        "opened": outr.total_opened,
        "replied": outr.total_replied,
        "bounced": outr.total_bounced,
        "open_rate": outr.open_rate,
        "reply_rate": outr.reply_rate,
        "bounce_rate": outr.bounce_rate,
        "funnel": {s.label: s.count for s in fn.stages},
        "by_channel": [b.model_dump() for b in outr.by_channel],
        "open_tasks": ov.open_tasks,
        "overdue_tasks": ov.overdue_tasks,
    }
    res = get_ai_service().analyze_campaign(stats)
    ai_log.record(db, res, workspace_id=ctx.workspace_id, created_by=ctx.user.id, facts=stats)
    db.commit()
    return InsightsResponse(result=AIResultOut(
        status=res.status, kind=res.kind or "analyze_campaign", model=res.model,
        output=res.output or {}, assumptions=res.assumptions or [],
        latency_ms=res.latency_ms, error=res.error,
    ))
