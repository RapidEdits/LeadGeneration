"""Schemas for connected email accounts, OAuth, test-send and deliverability."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SmtpConnectRequest(BaseModel):
    from_address: EmailStr
    from_name: str | None = None
    host: str = Field(min_length=1)
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool | None = None      # default inferred from port (587 => STARTTLS)
    use_ssl: bool = False
    # Optional IMAP for reply/bounce polling (falls back to SMTP host/creds if unset).
    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    imap_password: str | None = None
    imap_ssl: bool = True


class ConnectedAccountOut(BaseModel):
    id: str
    provider: str
    type: str
    display_name: str | None = None
    external_id: str | None = None
    status: str
    from_address: str | None = None
    from_name: str | None = None
    can_receive: bool = False        # inbound polling available (IMAP/Gmail/Graph)
    created_at: datetime

    model_config = {"from_attributes": True}


class TestSendRequest(BaseModel):
    to_address: EmailStr


class SimpleResult(BaseModel):
    ok: bool
    detail: str | None = None


class OAuthStartResponse(BaseModel):
    authorize_url: str


class DeliverabilityRequest(BaseModel):
    domain: str | None = None
    subject: str | None = None
    body: str | None = None


class DeliverabilityResponse(BaseModel):
    domain: dict | None = None
    content: dict | None = None
