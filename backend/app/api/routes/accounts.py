"""Connected email accounts: OAuth (Gmail/Microsoft), SMTP connect, test-send,
disconnect, and deliverability checks.

Credentials are encrypted at rest (Fernet); responses never include secrets.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.core.config import settings
from app.core.security import encrypt_json, sign_token, verify_token
from app.db.session import get_db
from app.models.enums import (
    AuditAction,
    ConnectedAccountStatus,
    ConnectedAccountType,
    WorkspaceRole,
)
from app.models.outreach import ConnectedAccount
from app.schemas.account import (
    ConnectedAccountOut,
    DeliverabilityRequest,
    DeliverabilityResponse,
    OAuthStartResponse,
    SimpleResult,
    SmtpConnectRequest,
    TestSendRequest,
)
from app.services import audit, deliverability, oauth
from app.services.email import factory, sender
from app.services.email.smtp import SmtpEmailProvider

router = APIRouter(prefix="/accounts", tags=["accounts"])

_OAUTH_STATE_MAX_AGE = 600  # seconds


def _to_out(a: ConnectedAccount) -> ConnectedAccountOut:
    meta = a.meta or {}
    can_receive = a.provider in ("gmail", "microsoft") or bool(meta.get("imap_host"))
    return ConnectedAccountOut(
        id=a.id, provider=a.provider, type=a.type.value,
        display_name=a.display_name, external_id=a.external_id, status=a.status.value,
        from_address=meta.get("from_address"), from_name=meta.get("from_name"),
        can_receive=can_receive, created_at=a.created_at,
    )


def _get_owned(db: Session, ws_id: str, account_id: str) -> ConnectedAccount:
    a = db.get(ConnectedAccount, account_id)
    if a is None or a.workspace_id != ws_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return a


@router.get("", response_model=list[ConnectedAccountOut])
def list_accounts(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[ConnectedAccountOut]:
    rows = db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == ctx.workspace_id,
            ConnectedAccount.type == ConnectedAccountType.email,
        ).order_by(ConnectedAccount.created_at.desc())
    ).scalars().all()
    return [_to_out(a) for a in rows]


@router.post("/smtp", response_model=ConnectedAccountOut, status_code=status.HTTP_201_CREATED)
def connect_smtp(
    payload: SmtpConnectRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin)),
    db: Session = Depends(get_db),
) -> ConnectedAccountOut:
    creds = {
        "host": payload.host, "port": payload.port,
        "username": payload.username, "password": payload.password,
        "use_tls": payload.use_tls if payload.use_tls is not None else (payload.port == 587),
        "use_ssl": payload.use_ssl,
        "imap_host": payload.imap_host, "imap_port": payload.imap_port,
        "imap_username": payload.imap_username, "imap_password": payload.imap_password,
        "imap_ssl": payload.imap_ssl,
    }
    ok, err = SmtpEmailProvider(creds).verify()
    meta = {
        "from_address": str(payload.from_address), "from_name": payload.from_name,
        "imap_host": payload.imap_host or (payload.host if payload.imap_password or payload.password else None),
    }
    account = ConnectedAccount(
        workspace_id=ctx.workspace_id,
        type=ConnectedAccountType.email,
        provider="smtp",
        display_name=payload.from_name or str(payload.from_address),
        external_id=str(payload.from_address),
        status=ConnectedAccountStatus.connected if ok else ConnectedAccountStatus.error,
        encrypted_credentials=encrypt_json(creds),
        meta=meta,
    )
    db.add(account)
    audit.record(db, action=AuditAction.create, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="connected_account", entity_id=account.id,
                 data={"provider": "smtp", "verified": ok})
    db.commit()
    db.refresh(account)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"SMTP verification failed: {err}")
    return _to_out(account)


@router.post("/{account_id}/test", response_model=SimpleResult)
def test_send(
    account_id: str,
    payload: TestSendRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> SimpleResult:
    _get_owned(db, ctx.workspace_id, account_id)
    try:
        result = sender.send_test_email(db, ctx.workspace_id, str(payload.to_address))
    except factory.NoEmailAccount as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    if not result.success:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.error or "Send failed")
    return SimpleResult(ok=True, detail="Test email sent")


@router.post("/{account_id}/verify", response_model=SimpleResult)
def verify_account(
    account_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> SimpleResult:
    account = _get_owned(db, ctx.workspace_id, account_id)
    ok, err = factory.build_provider(db, account).verify()
    account.status = ConnectedAccountStatus.connected if ok else ConnectedAccountStatus.error
    db.commit()
    return SimpleResult(ok=ok, detail=None if ok else err)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def disconnect(
    account_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin)),
    db: Session = Depends(get_db),
) -> None:
    account = _get_owned(db, ctx.workspace_id, account_id)
    db.delete(account)
    audit.record(db, action=AuditAction.delete, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="connected_account", entity_id=account_id)
    db.commit()


# ---- OAuth: Gmail + Microsoft ----

def _start(provider: str, ctx: WorkspaceContext) -> OAuthStartResponse:
    state = sign_token({"ws": ctx.workspace_id, "uid": ctx.user.id, "p": provider, "iat": time.time()})
    try:
        url = oauth.google_auth_url(state) if provider == "google" else oauth.microsoft_auth_url(state)
    except oauth.OAuthNotConfigured as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return OAuthStartResponse(authorize_url=url)


@router.get("/oauth/google/start", response_model=OAuthStartResponse)
def google_start(ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin))) -> OAuthStartResponse:
    return _start("google", ctx)


@router.get("/oauth/microsoft/start", response_model=OAuthStartResponse)
def microsoft_start(ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin))) -> OAuthStartResponse:
    return _start("microsoft", ctx)


def _oauth_callback(provider: str, code: str | None, state: str | None, db: Session) -> RedirectResponse:
    dest = f"{settings.APP_BASE_URL.rstrip('/')}/settings"

    def _redirect(status_str: str, msg: str = "") -> RedirectResponse:
        from urllib.parse import urlencode
        return RedirectResponse(f"{dest}?{urlencode({'email': status_str, 'msg': msg})}")

    payload = verify_token(state or "", max_age_seconds=_OAUTH_STATE_MAX_AGE)
    if not payload or payload.get("p") != provider:
        return _redirect("error", "Invalid or expired authorization state")
    if not code:
        return _redirect("error", "Authorization was cancelled")

    workspace_id = payload["ws"]
    try:
        creds = (oauth.exchange_google_code(code) if provider == "google"
                 else oauth.exchange_microsoft_code(code))
    except Exception as exc:  # noqa: BLE001
        return _redirect("error", f"Token exchange failed: {exc}")

    email_addr = creds.get("email") or ""
    prov = creds["provider"]
    # Upsert by (workspace, provider, external_id).
    existing = db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider == prov,
            ConnectedAccount.external_id == email_addr,
        )
    ).scalar_one_or_none()
    account = existing or ConnectedAccount(
        workspace_id=workspace_id, type=ConnectedAccountType.email, provider=prov,
    )
    account.display_name = email_addr
    account.external_id = email_addr
    account.status = ConnectedAccountStatus.connected
    account.encrypted_credentials = encrypt_json(creds)
    account.meta = {"from_address": email_addr, "from_name": None, "scope": creds.get("scope")}
    db.add(account)
    audit.record(db, action=AuditAction.create, workspace_id=workspace_id,
                 actor_id=payload.get("uid"), entity_type="connected_account",
                 entity_id=account.id, data={"provider": prov})
    db.commit()
    return _redirect("connected", email_addr)


@router.get("/oauth/google/callback", include_in_schema=False)
def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return _oauth_callback("google", code, state, db)


@router.get("/oauth/microsoft/callback", include_in_schema=False)
def microsoft_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return _oauth_callback("microsoft", code, state, db)


# ---- Deliverability ----

@router.post("/deliverability/check", response_model=DeliverabilityResponse)
def deliverability_check(
    payload: DeliverabilityRequest,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> DeliverabilityResponse:
    domain_report = deliverability.check_domain(payload.domain) if payload.domain else None
    content_report = (
        deliverability.check_content(payload.subject or "", payload.body or "")
        if (payload.subject or payload.body) else None
    )
    return DeliverabilityResponse(domain=domain_report, content=content_report)
