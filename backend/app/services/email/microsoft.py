"""Microsoft 365 / Outlook email provider via Microsoft Graph (sendMail).

Built with a valid access token by the factory. Graph's sendMail does not return a
message id in the response body, so we surface our own RFC Message-ID for threading.
"""
from __future__ import annotations

import httpx

from app.services.email.base import EmailMessage, EmailProvider, EmailSendResult
from email.utils import make_msgid

_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
_ME_URL = "https://graph.microsoft.com/v1.0/me"


class MicrosoftEmailProvider(EmailProvider):
    name = "microsoft"

    def __init__(self, access_token: str, from_address: str, from_name: str | None = None):
        self.access_token = access_token
        self.from_address = from_address
        self.from_name = from_name

    def send(self, msg: EmailMessage) -> EmailSendResult:
        rfc_id = msg.headers.get("Message-ID") or make_msgid()
        internet_headers = [
            {"name": k, "value": v}
            for k, v in msg.headers.items()
            # Graph rejects reserved headers; only custom `x-`/List-* pass through.
            if k.lower().startswith("x-") or k.lower().startswith("list-")
        ]
        payload = {
            "message": {
                "subject": msg.subject,
                "body": {"contentType": "HTML", "content": msg.html_body},
                "toRecipients": [{"emailAddress": {"address": msg.to_address}}],
                **({"replyTo": [{"emailAddress": {"address": msg.reply_to}}]} if msg.reply_to else {}),
                **({"internetMessageHeaders": internet_headers} if internet_headers else {}),
            },
            "saveToSentItems": True,
        }
        try:
            resp = httpx.post(
                _SENDMAIL_URL,
                headers={"Authorization": f"Bearer {self.access_token}"},
                json=payload,
                timeout=30,
            )
        except httpx.HTTPError as exc:
            return EmailSendResult(success=False, error=f"Graph request failed: {exc}")
        if resp.status_code >= 400:
            return EmailSendResult(success=False, error=f"Graph API {resp.status_code}: {resp.text[:300]}")
        return EmailSendResult(success=True, provider_message_id=rfc_id, rfc_message_id=rfc_id)

    def verify(self) -> tuple[bool, str | None]:
        try:
            resp = httpx.get(
                _ME_URL, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=15
            )
        except httpx.HTTPError as exc:
            return False, str(exc)
        if resp.status_code >= 400:
            return False, f"Graph API {resp.status_code}: {resp.text[:200]}"
        return True, None
