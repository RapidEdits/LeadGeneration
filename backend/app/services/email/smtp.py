"""SMTP email provider (also the local-dev live path via Mailpit).

Credentials shape (decrypted JSON from ConnectedAccount.encrypted_credentials):
    {"host","port","username","password","use_tls","use_ssl",
     "imap_host","imap_port","imap_username","imap_password","imap_ssl"}
Non-secret display config (from_address, from_name) lives in ConnectedAccount.meta.
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

from app.services.email.base import EmailMessage, EmailProvider, EmailSendResult


class SmtpEmailProvider(EmailProvider):
    name = "smtp"

    def __init__(self, creds: dict):
        self.host = creds.get("host") or ""
        self.port = int(creds.get("port") or 587)
        self.username = creds.get("username") or ""
        self.password = creds.get("password") or ""
        # Default to STARTTLS unless explicitly disabled; Mailpit dev uses neither.
        self.use_ssl = bool(creds.get("use_ssl", False))
        self.use_tls = bool(creds.get("use_tls", self.port == 587))

    def _connect(self) -> smtplib.SMTP:
        if self.use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(self.host, self.port, timeout=20)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=20)
            if self.use_tls:
                server.starttls(context=ssl.create_default_context())
        if self.username and self.password:
            server.login(self.username, self.password)
        return server

    def _build(self, msg: EmailMessage) -> tuple[MIMEMultipart, str]:
        mime = MIMEMultipart("alternative")
        mime["Subject"] = msg.subject
        mime["From"] = formataddr((msg.from_name or "", msg.from_address))
        mime["To"] = msg.to_address
        if msg.reply_to:
            mime["Reply-To"] = msg.reply_to
        rfc_id = msg.headers.get("Message-ID") or make_msgid()
        mime["Message-ID"] = rfc_id
        for k, v in msg.headers.items():
            if k.lower() == "message-id":
                continue
            mime[k] = v
        mime.attach(MIMEText(msg.text_body or "", "plain", "utf-8"))
        mime.attach(MIMEText(msg.html_body or "", "html", "utf-8"))
        return mime, rfc_id

    def send(self, msg: EmailMessage) -> EmailSendResult:
        if not self.host:
            return EmailSendResult(success=False, error="SMTP host not configured")
        mime, rfc_id = self._build(msg)
        try:
            server = self._connect()
        except Exception as exc:  # noqa: BLE001
            return EmailSendResult(success=False, error=f"SMTP connect failed: {exc}")
        try:
            refused = server.sendmail(msg.from_address, [msg.to_address], mime.as_string())
            # `sendmail` returns a dict of refused recipients (empty == all accepted).
            if refused:
                return EmailSendResult(
                    success=False, error=f"Recipient refused: {refused}", hard_bounce=True
                )
        except smtplib.SMTPRecipientsRefused as exc:
            return EmailSendResult(success=False, error=str(exc), hard_bounce=True)
        except Exception as exc:  # noqa: BLE001
            return EmailSendResult(success=False, error=f"SMTP send failed: {exc}")
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
        return EmailSendResult(success=True, provider_message_id=rfc_id, rfc_message_id=rfc_id)

    def verify(self) -> tuple[bool, str | None]:
        if not self.host:
            return False, "SMTP host not configured"
        try:
            server = self._connect()
            server.noop()
            server.quit()
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
