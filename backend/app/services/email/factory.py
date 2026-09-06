"""Resolve a workspace's connected email account into a live EmailProvider.

Handles OAuth access-token refresh (and persists the refreshed token) transparently,
so callers always receive a provider with a valid token.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_json, encrypt_json
from app.models.enums import ConnectedAccountStatus, ConnectedAccountType
from app.models.outreach import ConnectedAccount
from app.services import oauth
from app.services.email.base import EmailProvider
from app.services.email.gmail import GmailEmailProvider
from app.services.email.microsoft import MicrosoftEmailProvider
from app.services.email.smtp import SmtpEmailProvider

logger = logging.getLogger(__name__)

_REFRESH_MARGIN = 120  # refresh if the token expires within 2 minutes


class NoEmailAccount(RuntimeError):
    pass


def get_active_email_account(db: Session, workspace_id: str) -> ConnectedAccount | None:
    """The workspace's connected, sendable email account (most recently connected wins)."""
    return db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.type == ConnectedAccountType.email,
            ConnectedAccount.status == ConnectedAccountStatus.connected,
        ).order_by(ConnectedAccount.updated_at.desc()).limit(1)
    ).scalar_one_or_none()


def _ensure_fresh_oauth(db: Session, account: ConnectedAccount, creds: dict) -> dict:
    """Refresh an OAuth access token if it's expired/near-expiry, persisting the result."""
    expires_at = creds.get("expires_at", 0)
    if expires_at and time.time() < expires_at - _REFRESH_MARGIN:
        return creds
    refresh_token = creds.get("refresh_token")
    if not refresh_token:
        return creds  # nothing to refresh with; provider call will surface auth error
    if account.provider == "gmail":
        updated = oauth.refresh_google(refresh_token)
    elif account.provider == "microsoft":
        updated = oauth.refresh_microsoft(refresh_token)
    else:
        return creds
    creds.update(updated)
    account.encrypted_credentials = encrypt_json(creds)
    db.add(account)
    db.flush()
    return creds


def build_provider(db: Session, account: ConnectedAccount) -> EmailProvider:
    creds = decrypt_json(account.encrypted_credentials or "") or {}
    meta = account.meta or {}
    from_address = meta.get("from_address") or account.external_id or creds.get("email") or ""
    from_name = meta.get("from_name")

    if account.provider == "smtp":
        return SmtpEmailProvider(creds)
    if account.provider == "gmail":
        creds = _ensure_fresh_oauth(db, account, creds)
        return GmailEmailProvider(creds.get("access_token", ""), from_address, from_name)
    if account.provider == "microsoft":
        creds = _ensure_fresh_oauth(db, account, creds)
        return MicrosoftEmailProvider(creds.get("access_token", ""), from_address, from_name)
    raise NoEmailAccount(f"Unknown email provider: {account.provider}")


def resolve(db: Session, workspace_id: str) -> tuple[EmailProvider, ConnectedAccount]:
    account = get_active_email_account(db, workspace_id)
    if account is None:
        raise NoEmailAccount("No connected email account for this workspace")
    return build_provider(db, account), account


def fresh_credentials(db: Session, account: ConnectedAccount) -> dict:
    """Decrypted credentials with any OAuth access token refreshed + persisted."""
    creds = decrypt_json(account.encrypted_credentials or "") or {}
    if account.provider in ("gmail", "microsoft"):
        creds = _ensure_fresh_oauth(db, account, creds)
    return creds


def account_from_address(account: ConnectedAccount) -> tuple[str, str | None]:
    meta = account.meta or {}
    creds = decrypt_json(account.encrypted_credentials or "") or {}
    addr = meta.get("from_address") or account.external_id or creds.get("email") or ""
    return addr, meta.get("from_name")
