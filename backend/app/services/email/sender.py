"""The single email send path. Renders tracking + unsubscribe, then delegates to a
provider resolved from the workspace's connected account.

Called by the engine for live (non-test) email sends. The Message row must already
exist (and carry a tracking_id) so tracking URLs bind to it.
"""
from __future__ import annotations

from email.utils import make_msgid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.message import Message
from app.models.outreach import ConnectedAccount
from app.services.email import factory, tracking
from app.services.email.base import EmailMessage, EmailSendResult


def _render(message: Message, *, tracking_enabled: bool) -> tuple[str, str, dict[str, str]]:
    text_body = message.body or ""
    html_body = tracking.text_to_html(text_body)
    headers: dict[str, str] = {}
    if tracking_enabled and message.tracking_id:
        html_body = tracking.build_tracked_html(html_body, tracking_id=message.tracking_id)
        unsub = tracking.unsubscribe_url(message.tracking_id)
        headers["List-Unsubscribe"] = tracking.list_unsubscribe_header(message.tracking_id)
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        text_body = f"{text_body}\n\n—\nUnsubscribe: {unsub}"
    return html_body, text_body, headers


def send_campaign_message(db: Session, message: Message) -> EmailSendResult:
    """Send a persisted outbound email Message via the workspace's connected account."""
    provider, account = factory.resolve(db, message.workspace_id)
    from_address, from_name = factory.account_from_address(account)

    html_body, text_body, headers = _render(message, tracking_enabled=settings.EMAIL_TRACKING_ENABLED)
    headers["Message-ID"] = make_msgid()

    em = EmailMessage(
        to_address=message.to_address or "",
        subject=message.subject or "",
        html_body=html_body,
        text_body=text_body,
        from_address=from_address,
        from_name=from_name,
        reply_to=from_address or None,
        headers=headers,
    )
    result = provider.send(em)
    if result.rfc_message_id:
        message.rfc_message_id = result.rfc_message_id
    meta = dict(message.meta or {})
    meta["email_provider"] = account.provider
    meta["from_address"] = from_address
    message.meta = meta
    return result


def send_test_email(
    db: Session, workspace_id: str, to_address: str, account: ConnectedAccount | None = None
) -> EmailSendResult:
    """Ad-hoc deliverability smoke test from the connected account (no tracking/campaign).

    Pass `account` to test a specific connected account; otherwise the workspace's
    most recently connected one is used.
    """
    if account is None:
        provider, account = factory.resolve(db, workspace_id)
    else:
        provider = factory.build_provider(db, account)
    from_address, from_name = factory.account_from_address(account)
    em = EmailMessage(
        to_address=to_address,
        subject="Test email from Lead Generator",
        html_body=tracking.text_to_html(
            "This is a test email confirming your connected account can send.\n\n"
            "If you received this, sending is working correctly."
        ),
        text_body="This is a test email confirming your connected account can send.",
        from_address=from_address,
        from_name=from_name,
        reply_to=from_address or None,
        headers={"Message-ID": make_msgid()},
    )
    return provider.send(em)
