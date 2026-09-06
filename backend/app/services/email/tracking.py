"""Open-pixel, click-tracking and unsubscribe URL construction + HTML rewriting.

All public URLs point at PUBLIC_BASE_URL (the tracking router, mounted without auth).
- Open pixel:   GET /t/o/{tracking_id}.gif      -> records `opened`
- Click:        GET /t/c/{tracking_id}?u=<b64>&s=<sig> -> records `clicked`, 302 to target
- Unsubscribe:  GET /u/{tracking_id}             -> confirm page; POST -> suppress

The click target is HMAC-signed so the endpoint can never be turned into an open
redirect. `tracking_id` itself is an unguessable capability token (per message).
"""
from __future__ import annotations

import html as _html
import re
from urllib.parse import quote

from app.core.config import settings
from app.core.security import sign_token, verify_token

# A single transparent 1x1 GIF.
PIXEL_GIF = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000"
    "010001000002024401003b"
)

_A_HREF = re.compile(r'(<a\b[^>]*?\bhref=")(https?://[^"]+)(")', re.IGNORECASE)


def _base() -> str:
    return settings.PUBLIC_BASE_URL.rstrip("/")


def open_pixel_url(tracking_id: str) -> str:
    return f"{_base()}/t/o/{tracking_id}.gif"


def unsubscribe_url(tracking_id: str) -> str:
    return f"{_base()}/u/{tracking_id}"


def click_url(tracking_id: str, target: str) -> str:
    sig = sign_token({"u": target})
    return f"{_base()}/t/c/{tracking_id}?s={quote(sig, safe='')}"


def verify_click(sig: str) -> str | None:
    payload = verify_token(sig)
    return payload.get("u") if payload else None


def list_unsubscribe_header(tracking_id: str) -> str:
    return f"<{unsubscribe_url(tracking_id)}>"


def rewrite_links(html_body: str, tracking_id: str) -> str:
    """Rewrite absolute http(s) <a href> targets to signed click-tracking URLs."""
    def _sub(m: re.Match[str]) -> str:
        return f"{m.group(1)}{click_url(tracking_id, m.group(2))}{m.group(3)}"

    return _A_HREF.sub(_sub, html_body)


def text_to_html(text: str) -> str:
    """Minimal, safe text->HTML: escape, linkify bare URLs, preserve line breaks."""
    escaped = _html.escape(text or "")
    escaped = re.sub(
        r"(https?://[^\s<]+)",
        r'<a href="\1">\1</a>',
        escaped,
    )
    body = escaped.replace("\n", "<br>\n")
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'font-size:15px;line-height:1.5;color:#111">'
        f"{body}</div>"
    )


def build_tracked_html(
    html_body: str,
    *,
    tracking_id: str,
    add_open_pixel: bool = True,
    add_unsubscribe_footer: bool = True,
) -> str:
    """Return html with links rewritten, an unsubscribe footer, and an open pixel."""
    out = rewrite_links(html_body, tracking_id)
    if add_unsubscribe_footer:
        url = unsubscribe_url(tracking_id)
        out += (
            '<div style="margin-top:24px;padding-top:12px;border-top:1px solid #eee;'
            'font-size:12px;color:#888">'
            f'If you\'d prefer not to receive these emails, <a href="{url}" '
            'style="color:#888">unsubscribe here</a>.</div>'
        )
    if add_open_pixel:
        out += (
            f'<img src="{open_pixel_url(tracking_id)}" width="1" height="1" '
            'alt="" style="display:none" />'
        )
    return out
