"""Gmail API email provider. Sends via users.messages.send (raw RFC822).

Built with a *valid* access token by the factory (which handles refresh + persistence),
so this class stays stateless w.r.t. the DB.
"""
from __future__ import annotations

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

import httpx

from app.services.email.base import EmailMessage, EmailProvider, EmailSendResult

_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"


class GmailEmailProvider(EmailProvider):
    name = "gmail"

    def __init__(self, access_token: str, from_address: str, from_name: str | None = None):
        self.access_token = access_token
        self.from_address = from_address
        self.from_name = from_name

    def _raw(self, msg: EmailMessage) -> tuple[str, str]:
        mime = MIMEMultipart("alternative")
        mime["Subject"] = msg.subject
        mime["From"] = formataddr((msg.from_name or self.from_name or "", msg.from_address))
        mime["To"] = msg.to_address
        if msg.reply_to:
            mime["Reply-To"] = msg.reply_to
        rfc_id = msg.headers.get("Message-ID") or make_msgid()
        mime["Message-ID"] = rfc_id
        for k, v in msg.headers.items():
            if k.lower() != "message-id":
                mime[k] = v
        mime.attach(MIMEText(msg.text_body or "", "plain", "utf-8"))
        mime.attach(MIMEText(msg.html_body or "", "html", "utf-8"))
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        return raw, rfc_id

    def send(self, msg: EmailMessage) -> EmailSendResult:
        raw, rfc_id = self._raw(msg)
        try:
            resp = httpx.post(
                _SEND_URL,
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={"raw": raw},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            return EmailSendResult(success=False, error=f"Gmail request failed: {exc}")
        if resp.status_code >= 400:
            return EmailSendResult(success=False, error=f"Gmail API {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return EmailSendResult(
            success=True, provider_message_id=data.get("id"), rfc_message_id=rfc_id
        )

    def verify(self) -> tuple[bool, str | None]:
        try:
            resp = httpx.get(
                _PROFILE_URL,
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=15,
            )
        except httpx.HTTPError as exc:
            return False, str(exc)
        if resp.status_code >= 400:
            return False, f"Gmail API {resp.status_code}: {resp.text[:200]}"
        return True, None
