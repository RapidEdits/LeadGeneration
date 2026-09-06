"""Inbox: inbound messages (replies) across the workspace, plus a manual poll trigger."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.db.session import get_db
from app.models.enums import Channel, MessageDirection, WorkspaceRole
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
    created_at: datetime


@router.get("", response_model=list[InboxItem])
def list_inbox(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[InboxItem]:
    rows = db.execute(
        select(Message, Lead)
        .join(Lead, Lead.id == Message.lead_id, isouter=True)
        .where(
            Message.workspace_id == ctx.workspace_id,
            Message.direction == MessageDirection.inbound,
        )
        .order_by(Message.created_at.desc())
        .limit(200)
    ).all()
    out: list[InboxItem] = []
    for msg, lead in rows:
        meta = msg.meta or {}
        out.append(InboxItem(
            id=msg.id, channel=msg.channel, subject=msg.subject, body=msg.body,
            from_address=meta.get("from_address"),
            lead_id=msg.lead_id, lead_name=lead.full_name if lead else None,
            campaign_id=msg.campaign_id, created_at=msg.created_at,
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
