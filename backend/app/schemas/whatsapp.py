"""Schemas for the WhatsApp subsystem (Phase 6): session connect/status + inbound webhook."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WhatsAppSession(BaseModel):
    """Live pairing state, reconciled from the microservice on each poll."""

    status: str                       # disconnected | qr | connected | error
    qr: str | None = None             # data-URL of the pairing QR while status == "qr"
    me: str | None = None             # connected number, once paired
    mode: str | None = None           # live | mock | unknown
    error: str | None = None
    account_id: str | None = None     # the ConnectedAccount backing this session, if any
    connected_at: datetime | None = None


class WhatsAppWebhookIn(BaseModel):
    # The microservice posts JSON key "from" (a Python keyword) — alias it.
    from_: str | None = Field(default=None, alias="from")
    body: str | None = None
    provider_message_id: str | None = None
    timestamp: int | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class SimpleOk(BaseModel):
    ok: bool = True
    detail: str | None = None
