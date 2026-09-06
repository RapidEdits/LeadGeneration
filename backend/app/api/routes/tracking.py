"""Public (unauthenticated) tracking endpoints. The per-message `tracking_id` is the
capability — unguessable, so no auth is needed or wanted (recipients aren't users).

Mounted at the root (not /api/v1) for short, clean URLs in outbound mail.
"""
from __future__ import annotations

import html as _html

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import MessageEventType, MessageStatus, Provenance
from app.models.message import Message, MessageEvent
from app.models.outreach import UnsubscribeEvent
from app.services import suppression
from app.services.email.tracking import PIXEL_GIF, verify_click
from app.models.enums import SuppressionReason

router = APIRouter(tags=["tracking"])

_NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, private",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _message_by_tracking(db: Session, tracking_id: str) -> Message | None:
    return db.execute(
        select(Message).where(Message.tracking_id == tracking_id).limit(1)
    ).scalar_one_or_none()


def _has_event(db: Session, message_id: str, etype: MessageEventType) -> bool:
    return db.execute(
        select(MessageEvent.id).where(
            MessageEvent.message_id == message_id, MessageEvent.type == etype
        ).limit(1)
    ).first() is not None


def _pixel() -> Response:
    return Response(content=PIXEL_GIF, media_type="image/gif", headers=_NO_CACHE)


@router.get("/t/o/{tracking_id}.gif", include_in_schema=False)
def track_open(tracking_id: str, request: Request, db: Session = Depends(get_db)) -> Response:
    msg = _message_by_tracking(db, tracking_id)
    if msg and not _has_event(db, msg.id, MessageEventType.opened):
        db.add(MessageEvent(
            workspace_id=msg.workspace_id, message_id=msg.id,
            type=MessageEventType.opened, provenance=Provenance.observed,
            detail={"ua": request.headers.get("user-agent", "")[:300]},
        ))
        if msg.status in (MessageStatus.sent, MessageStatus.delivered):
            msg.status = MessageStatus.opened
        db.commit()
    return _pixel()


@router.get("/t/c/{tracking_id}", include_in_schema=False)
def track_click(
    tracking_id: str,
    request: Request,
    s: str = Query(...),
    db: Session = Depends(get_db),
) -> Response:
    target = verify_click(s)
    if not target:
        return Response(status_code=400, content="Invalid link")
    msg = _message_by_tracking(db, tracking_id)
    if msg:
        db.add(MessageEvent(
            workspace_id=msg.workspace_id, message_id=msg.id,
            type=MessageEventType.clicked, provenance=Provenance.observed,
            detail={"url": target, "ua": request.headers.get("user-agent", "")[:300]},
        ))
        db.commit()
    return RedirectResponse(target, status_code=302)


def _do_unsubscribe(db: Session, msg: Message, request: Request, method: str) -> None:
    if not msg.to_address:
        return
    suppression.add_suppression(
        db, msg.workspace_id, "email", msg.to_address,
        SuppressionReason.unsubscribed, note="Recipient unsubscribed",
    )
    db.add(UnsubscribeEvent(
        workspace_id=msg.workspace_id, channel="email", value=msg.to_address,
        lead_id=msg.lead_id, message_id=msg.id, campaign_id=msg.campaign_id, method=method,
        source_ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent", "")[:500],
    ))
    db.add(MessageEvent(
        workspace_id=msg.workspace_id, message_id=msg.id,
        type=MessageEventType.unsubscribed, provenance=Provenance.observed,
        detail={"method": method},
    ))
    db.commit()


_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unsubscribe</title>
<style>body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f6f7f9;
color:#111;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:32px;max-width:420px;
text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
button{{background:#111;color:#fff;border:0;border-radius:8px;padding:10px 20px;font-size:15px;
cursor:pointer}}h1{{font-size:19px;margin:0 0 8px}}p{{color:#555;font-size:14px;line-height:1.5}}
</style></head><body><div class="card">{content}</div></body></html>"""


@router.get("/u/{tracking_id}", include_in_schema=False)
def unsubscribe_page(tracking_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    msg = _message_by_tracking(db, tracking_id)
    if not msg:
        return HTMLResponse(_PAGE.format(content="<h1>Link not found</h1><p>This unsubscribe link is no longer valid.</p>"))
    already = _has_event(db, msg.id, MessageEventType.unsubscribed)
    if already:
        return HTMLResponse(_PAGE.format(content="<h1>You're unsubscribed</h1><p>You won't receive further emails.</p>"))
    content = (
        f"<h1>Unsubscribe</h1>"
        f"<p>Stop receiving emails at <b>{_html.escape(msg.to_address or '')}</b>?</p>"
        f'<form method="post" action="/u/{tracking_id}"><button type="submit">Unsubscribe</button></form>'
    )
    return HTMLResponse(_PAGE.format(content=content))


@router.post("/u/{tracking_id}", include_in_schema=False)
def unsubscribe_confirm(
    tracking_id: str, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    msg = _message_by_tracking(db, tracking_id)
    if msg and not _has_event(db, msg.id, MessageEventType.unsubscribed):
        # RFC 8058 one-click sends List-Unsubscribe=One-Click; a human form posts too.
        # Guard on the event so repeat POSTs don't stack duplicate unsubscribe rows.
        _do_unsubscribe(db, msg, request, method="link")
    return HTMLResponse(_PAGE.format(content="<h1>You're unsubscribed</h1><p>You won't receive further emails.</p>"))
