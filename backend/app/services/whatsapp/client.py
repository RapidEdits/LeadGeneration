"""Thin HTTP client for the internal whatsapp-service microservice.

Isolated here so the provider and routes stay transport-agnostic and tests can
stub a single seam. Every call carries the internal shared-secret token; the
service is never reachable publicly.
"""
from __future__ import annotations

import httpx

from app.core.config import settings

_TIMEOUT = 30.0


class WhatsAppServiceError(RuntimeError):
    """The whatsapp-service is unreachable or returned an error."""


def _headers() -> dict[str, str]:
    return {"X-Service-Token": settings.WHATSAPP_SERVICE_TOKEN, "Content-Type": "application/json"}


def _url(path: str) -> str:
    return f"{settings.WHATSAPP_SERVICE_URL.rstrip('/')}{path}"


def session_status() -> dict:
    """{status, qr, me, mode, error}. Never raises — a down service reads as disconnected."""
    try:
        r = httpx.get(_url("/session/status"), headers=_headers(), timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"status": "disconnected", "qr": None, "me": None, "mode": "unknown", "error": str(exc)}


def session_start() -> dict:
    try:
        r = httpx.post(_url("/session/start"), headers=_headers(), timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise WhatsAppServiceError(f"Could not start WhatsApp session: {exc}") from exc


def session_logout() -> dict:
    try:
        r = httpx.post(_url("/session/logout"), headers=_headers(), timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise WhatsAppServiceError(f"Could not stop WhatsApp session: {exc}") from exc


def send(to: str, body: str) -> dict:
    """Send a text message. Returns {success, id} or raises WhatsAppServiceError."""
    try:
        r = httpx.post(
            _url("/messages/send"), headers=_headers(),
            json={"to": to, "body": body}, timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise WhatsAppServiceError(f"WhatsApp service unreachable: {exc}") from exc
    if r.status_code >= 400:
        detail = ""
        try:
            detail = r.json().get("error", "")
        except Exception:  # noqa: BLE001
            detail = r.text
        raise WhatsAppServiceError(detail or f"Send failed (HTTP {r.status_code})")
    return r.json()
