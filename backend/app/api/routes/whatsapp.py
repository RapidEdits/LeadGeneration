"""WhatsApp (Phase 6): connect a session (QR pairing), poll status, disconnect,
and receive inbound messages from the microservice.

Sending is automated (engine → WhatsAppProvider → microservice → OpenWA); these
endpoints manage the session lifecycle and ingest replies. The webhook is
authenticated by the internal service token, not a user JWT.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.core.config import settings
from app.db.session import get_db
from app.models.enums import (
    AuditAction,
    ConnectedAccountStatus,
    ConnectedAccountType,
    WorkspaceRole,
)
from app.models.outreach import ConnectedAccount
from app.schemas.whatsapp import SimpleOk, WhatsAppSession, WhatsAppWebhookIn
from app.services import audit
from app.services.whatsapp import client
from app.services.whatsapp import inbound as wa_inbound

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


def _get_account(db: Session, workspace_id: str) -> ConnectedAccount | None:
    return db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.type == ConnectedAccountType.whatsapp,
        ).order_by(ConnectedAccount.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def _reconcile(db: Session, workspace_id: str, live: dict) -> ConnectedAccount | None:
    """Make the ConnectedAccount reflect the microservice's live session state."""
    account = _get_account(db, workspace_id)
    live_status = live.get("status")
    if live_status == "connected":
        if account is None:
            account = ConnectedAccount(
                workspace_id=workspace_id, type=ConnectedAccountType.whatsapp, provider="openwa",
            )
            db.add(account)
        account.status = ConnectedAccountStatus.connected
        account.external_id = live.get("me")
        account.display_name = live.get("me") or "WhatsApp"
        account.meta = {"me": live.get("me"), "mode": live.get("mode")}
    elif account is not None and account.status == ConnectedAccountStatus.connected:
        # Service dropped the session — reflect that so can_send stops allowing sends.
        account.status = ConnectedAccountStatus.disconnected
    db.commit()
    if account is not None:
        db.refresh(account)
    return account


def _session_out(live: dict, account: ConnectedAccount | None) -> WhatsAppSession:
    return WhatsAppSession(
        status=live.get("status", "disconnected"),
        qr=live.get("qr"),
        me=live.get("me"),
        mode=live.get("mode"),
        error=live.get("error"),
        account_id=account.id if account else None,
        connected_at=account.updated_at if account and account.status == ConnectedAccountStatus.connected else None,
    )


@router.get("/session", response_model=WhatsAppSession)
def get_session(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> WhatsAppSession:
    live = client.session_status()
    account = _reconcile(db, ctx.workspace_id, live)
    return _session_out(live, account)


@router.post("/connect", response_model=WhatsAppSession)
def connect(
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin)),
    db: Session = Depends(get_db),
) -> WhatsAppSession:
    try:
        live = client.session_start()
    except client.WhatsAppServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    account = _reconcile(db, ctx.workspace_id, live)
    audit.record(db, action=AuditAction.create, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="connected_account",
                 entity_id=account.id if account else None,
                 data={"provider": "openwa", "type": "whatsapp", "status": live.get("status")})
    db.commit()
    return _session_out(live, account)


@router.post("/disconnect", response_model=SimpleOk)
def disconnect(
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin)),
    db: Session = Depends(get_db),
) -> SimpleOk:
    try:
        client.session_logout()
    except client.WhatsAppServiceError:
        pass  # tear down our record regardless of the service's state
    account = _get_account(db, ctx.workspace_id)
    if account is not None:
        account.status = ConnectedAccountStatus.disconnected
        audit.record(db, action=AuditAction.update, workspace_id=ctx.workspace_id,
                     actor_id=ctx.user.id, entity_type="connected_account", entity_id=account.id,
                     data={"status": "disconnected"})
        db.commit()
    return SimpleOk(detail="WhatsApp disconnected")


@router.post("/webhook", response_model=SimpleOk, include_in_schema=False)
def webhook(
    payload: WhatsAppWebhookIn,
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
    db: Session = Depends(get_db),
) -> SimpleOk:
    """Inbound message from the microservice. Authenticated by the internal token."""
    if not settings.WHATSAPP_SERVICE_TOKEN or x_service_token != settings.WHATSAPP_SERVICE_TOKEN:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")

    # Single session → resolve the owning workspace from the connected account.
    account = db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.type == ConnectedAccountType.whatsapp,
            ConnectedAccount.status == ConnectedAccountStatus.connected,
        ).order_by(ConnectedAccount.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    if account is None or not payload.from_:
        return SimpleOk(ok=False, detail="no connected WhatsApp workspace")

    outcome = wa_inbound.record_inbound(
        db, account.workspace_id, from_number=payload.from_,
        body=payload.body or "", provider_message_id=payload.provider_message_id,
    )
    db.commit()
    return SimpleOk(ok=outcome == "reply_recorded", detail=outcome)
