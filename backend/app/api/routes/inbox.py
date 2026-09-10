"""Inbox: inbound messages (replies) across the workspace, plus a manual poll trigger."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.db.session import get_db
from app.models.enums import Channel, MessageDirection, MessageStatus, WorkspaceRole
from app.models.campaign import Campaign
from app.models.message import MessageEvent
from app.models.lead import Lead
from app.models.message import Message

router = APIRouter(prefix="/inbox", tags=["inbox"])


class InboxItem(BaseModel):
    id: str
    channel: Channel
    subject: str | None = None
    body: str | None = None
    from_address: str | None = None
    lead_id: str | None = None
    lead_name: str | None = None
    campaign_id: str | None = None
    campaign_name: str | None = None
    direction: MessageDirection
    status: MessageStatus
    to_address: str | None = None
    events: list[dict] = []
    created_at: datetime


@router.get("", response_model=list[InboxItem])
def list_inbox(
    campaign_id: str | None = None,
    direction: MessageDirection | None = MessageDirection.inbound,
    channel: Channel | None = None,
    message_status: MessageStatus | None = None,
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(50, ge=1, le=200),
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[InboxItem]:
    query = (
        select(Message, Lead, Campaign.name)
        .join(Lead, Lead.id == Message.lead_id, isouter=True)
        .join(Campaign, (Campaign.id == Message.campaign_id) & (Campaign.workspace_id == ctx.workspace_id), isouter=True)
        .where(
            Message.workspace_id == ctx.workspace_id,
        )
    )
    if campaign_id:
        query = query.where(Message.campaign_id == campaign_id)
    if direction:
        query = query.where(Message.direction == direction)
    if channel:
        query = query.where(Message.channel == channel)
    if message_status:
        query = query.where(Message.status == message_status)
    rows = db.execute(query.order_by(Message.created_at.desc(), Message.id.desc()).offset(offset).limit(limit)).all()
    events: dict[str, list] = {}
    if rows:
        for event in db.scalars(select(MessageEvent).where(MessageEvent.workspace_id == ctx.workspace_id,
                MessageEvent.message_id.in_([m.id for m, _, _ in rows])).order_by(MessageEvent.created_at)):
            events.setdefault(event.message_id, []).append({"type": event.type.value,
                "created_at": event.created_at.isoformat(), "provenance": event.provenance.value,
                "error": (event.detail or {}).get("error")})
    out: list[InboxItem] = []
    for msg, lead, campaign_name in rows:
        meta = msg.meta or {}
        out.append(InboxItem(
            id=msg.id, channel=msg.channel, subject=msg.subject, body=msg.body,
            from_address=meta.get("from_address"),
            lead_id=msg.lead_id, lead_name=lead.full_name if lead else None,
            campaign_id=msg.campaign_id, created_at=msg.created_at,
            campaign_name=campaign_name, direction=msg.direction, status=msg.status,
            to_address=msg.to_address, events=events.get(msg.id, []),
        ))
    return out


class PollResult(BaseModel):
    outcomes: dict[str, int]


@router.post("/poll", response_model=PollResult)
def trigger_poll(
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> PollResult:
    """Manually poll this workspace's connected accounts for replies/bounces now."""
    from app.models.enums import ConnectedAccountStatus, ConnectedAccountType
    from app.models.outreach import ConnectedAccount
    from app.services import inbound

    accounts = db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == ctx.workspace_id,
            ConnectedAccount.type == ConnectedAccountType.email,
            ConnectedAccount.status == ConnectedAccountStatus.connected,
        )
    ).scalars().all()
    totals: dict[str, int] = {}
    for account in accounts:
        for k, v in inbound.poll_account(db, account).items():
            totals[k] = totals.get(k, 0) + v
    db.commit()
    return PollResult(outcomes=totals)
