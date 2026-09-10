"""Campaign email cohort reporting, excluding simulation from real performance."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Date, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.enums import Channel, MessageDirection, MessageEventType, MessageStatus, Provenance
from app.models.message import Message, MessageEvent
from app.services.message_metrics import real_message

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/email")
def email_metrics(campaign_id: str | None = None, days: int = Query(30, ge=1, le=180),
                  ctx: WorkspaceContext = Depends(get_workspace_context), db: Session = Depends(get_db)):
    if campaign_id and not db.scalar(select(Campaign.id).where(
        Campaign.id == campaign_id, Campaign.workspace_id == ctx.workspace_id)):
        raise HTTPException(404, "Campaign not found")
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    # Each event type contributes at most once per outbound message, even after repeat opens/replies.
    event_types = ["sent", "delivered", "opened", "clicked", "replied", "bounced", "unsubscribed"]
    ev = select(MessageEvent.message_id, *[
        func.max(case((MessageEvent.type == MessageEventType(t), 1), else_=0)).label(t)
        for t in event_types
    ]).where(MessageEvent.workspace_id == ctx.workspace_id,
             MessageEvent.provenance == Provenance.observed,
             MessageEvent.created_at <= now).group_by(MessageEvent.message_id).subquery()
    real = real_message()
    accepted = real & or_(Message.status.in_([MessageStatus.sent, MessageStatus.delivered,
        MessageStatus.opened, MessageStatus.replied]), ev.c.sent == 1)
    flags = {
        "sent": accepted,
        "delivered": accepted & or_(ev.c.delivered == 1, Message.status == MessageStatus.delivered),
        "opened": accepted & or_(ev.c.opened == 1, Message.status == MessageStatus.opened),
        "clicked": accepted & (ev.c.clicked == 1),
        "replied": accepted & or_(ev.c.replied == 1, Message.status == MessageStatus.replied),
        "bounced": real & or_(ev.c.bounced == 1, Message.status == MessageStatus.bounced),
        "unsubscribed": accepted & (ev.c.unsubscribed == 1),
        "failed": real & (Message.status == MessageStatus.failed),
        "queued": real & Message.status.in_([MessageStatus.queued, MessageStatus.pending_action]),
        "simulated": ~real,
        "attempted": real & or_(accepted, Message.status.in_([MessageStatus.failed, MessageStatus.bounced])),
    }
    columns = [func.sum(case((condition, 1), else_=0)).label(name) for name, condition in flags.items()]
    where = [Message.workspace_id == ctx.workspace_id, Message.channel == Channel.email,
             Message.direction == MessageDirection.outbound, Message.created_at >= start, Message.created_at <= now]
    if campaign_id:
        where.append(Message.campaign_id == campaign_id)
    base = select(*columns).select_from(Message).outerjoin(ev, ev.c.message_id == Message.id).where(*where)
    totals = {k: int(v or 0) for k, v in db.execute(base).mappings().one().items()}
    date = cast(Message.created_at, Date)
    daily = {str(row["date"]): dict(row) for row in db.execute(
        base.add_columns(date.label("date")).group_by(date)
    ).mappings()}
    points = []
    for i in range(days):
        day = str((start + timedelta(days=i)).date())
        points.append({"date": day, **{key: int(daily.get(day, {}).get(key) or 0) for key in flags}})
    rates = {f"{key}_rate": round(totals[key] / totals["sent"], 4) if totals["sent"] else 0
             for key in ("opened", "clicked", "replied", "unsubscribed")}
    rates["bounce_rate"] = round(totals["bounced"] / totals["attempted"], 4) if totals["attempted"] else 0
    return {"campaign_id": campaign_id, "days": days, "totals": totals, "rates": rates, "points": points,
            "definition": "Outbound email created in the selected UTC date window; engagement through now. Sent means provider accepted. Opens and clicks are observed tracking signals, not proof of a person reading. Delivery is shown only when confirmed. Each email counts once per engagement type."}
