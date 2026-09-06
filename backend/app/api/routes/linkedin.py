"""Assisted-LinkedIn (Phase 5): connect an identity + work the manual send/reply queue.

LinkedIn cold outreach can't be automated compliantly, so live LinkedIn steps are
queued as manual tasks (see `app.services.linkedin.tasks`). These endpoints let an
operator connect the sending identity, list open tasks, confirm a send, skip one,
and log a reply received on LinkedIn.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.db.session import get_db
from app.models.enums import (
    AuditAction,
    ConnectedAccountStatus,
    ConnectedAccountType,
    WorkspaceRole,
)
from app.models.outreach import ConnectedAccount
from app.schemas.linkedin import (
    CompleteTaskRequest,
    LinkedInAccountOut,
    LinkedInConnectRequest,
    LinkedInTaskOut,
    LogReplyRequest,
    SimpleOk,
    SkipTaskRequest,
)
from app.services import audit
from app.services.linkedin import tasks as li_tasks

router = APIRouter(prefix="/linkedin", tags=["linkedin"])


def _account_out(a: ConnectedAccount) -> LinkedInAccountOut:
    meta = a.meta or {}
    return LinkedInAccountOut(
        id=a.id, provider=a.provider, display_name=a.display_name,
        profile_url=meta.get("profile_url") or a.external_id,
        status=a.status.value, created_at=a.created_at,
    )


# ---- Identity ----

@router.get("/account", response_model=list[LinkedInAccountOut])
def list_accounts(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[LinkedInAccountOut]:
    rows = db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == ctx.workspace_id,
            ConnectedAccount.type == ConnectedAccountType.linkedin,
        ).order_by(ConnectedAccount.created_at.desc())
    ).scalars().all()
    return [_account_out(a) for a in rows]


@router.post("/account", response_model=LinkedInAccountOut, status_code=status.HTTP_201_CREATED)
def connect_account(
    payload: LinkedInConnectRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin)),
    db: Session = Depends(get_db),
) -> LinkedInAccountOut:
    account = ConnectedAccount(
        workspace_id=ctx.workspace_id,
        type=ConnectedAccountType.linkedin,
        provider="assisted",
        display_name=payload.display_name,
        external_id=payload.profile_url,
        status=ConnectedAccountStatus.connected,
        meta={"profile_url": payload.profile_url},
    )
    db.add(account)
    audit.record(db, action=AuditAction.create, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="connected_account", entity_id=account.id,
                 data={"provider": "assisted", "type": "linkedin"})
    db.commit()
    db.refresh(account)
    return _account_out(account)


@router.delete("/account/{account_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def disconnect_account(
    account_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin)),
    db: Session = Depends(get_db),
) -> None:
    a = db.get(ConnectedAccount, account_id)
    if a is None or a.workspace_id != ctx.workspace_id or a.type != ConnectedAccountType.linkedin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    db.delete(a)
    audit.record(db, action=AuditAction.delete, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="connected_account", entity_id=account_id)
    db.commit()


# ---- Task queue ----

@router.get("/tasks", response_model=list[LinkedInTaskOut])
def list_tasks(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[LinkedInTaskOut]:
    out: list[LinkedInTaskOut] = []
    for t in li_tasks.list_tasks(db, ctx.workspace_id):
        meta = t.message.meta or {}
        out.append(LinkedInTaskOut(
            id=t.message.id,
            lead_id=t.message.lead_id,
            lead_name=t.lead.full_name if t.lead else None,
            lead_title=t.lead.title if t.lead else None,
            profile_url=(t.lead.linkedin_url if t.lead else None) or t.message.to_address,
            campaign_id=t.message.campaign_id,
            campaign_name=t.campaign.name if t.campaign else None,
            body=t.message.body,
            created_at=t.message.created_at,
        ))
    return out


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, li_tasks.TaskNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.post("/tasks/{message_id}/complete", response_model=SimpleOk)
def complete_task(
    message_id: str,
    payload: CompleteTaskRequest | None = None,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> SimpleOk:
    try:
        li_tasks.complete_task(db, ctx.workspace_id, message_id,
                               actor_id=ctx.user.id, note=payload.note if payload else None)
    except (li_tasks.TaskNotFound, li_tasks.TaskNotOpen) as exc:
        raise _handle(exc)
    return SimpleOk(detail="Marked as sent")


@router.post("/tasks/{message_id}/skip", response_model=SimpleOk)
def skip_task(
    message_id: str,
    payload: SkipTaskRequest | None = None,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> SimpleOk:
    try:
        li_tasks.skip_task(db, ctx.workspace_id, message_id,
                           actor_id=ctx.user.id, reason=payload.reason if payload else None)
    except (li_tasks.TaskNotFound, li_tasks.TaskNotOpen) as exc:
        raise _handle(exc)
    return SimpleOk(detail="Task skipped")


@router.post("/tasks/{message_id}/reply", response_model=SimpleOk)
def log_reply(
    message_id: str,
    payload: LogReplyRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> SimpleOk:
    try:
        li_tasks.log_reply(db, ctx.workspace_id, message_id,
                           text=payload.text, from_name=payload.from_name, actor_id=ctx.user.id)
    except li_tasks.TaskNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return SimpleOk(detail="Reply logged")
