"""Inbound email polling: reply detection (halts the sequence) and bounce detection
(auto-suppresses + marks the member bounced). Normalizes every provider into one
`InboundEmail` shape, then collapses to Message + MessageEvent rows.

Parsing/classification/matching are pure and unit-tested; network fetch is per provider
(IMAP for SMTP accounts; Gmail API / Microsoft Graph for OAuth accounts). Idempotent:
an inbound message already stored (by RFC Message-ID) is skipped on re-poll.
"""
from __future__ import annotations

import base64
import email
import imaplib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import Message as PyEmailMessage
from email.utils import getaddresses, parseaddr

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import CampaignLead
from app.models.enums import (
    CampaignLeadState,
    Channel,
    LeadStatus,
    MessageDirection,
    MessageEventType,
    MessageStatus,
    Provenance,
    SuppressionReason,
)
from app.models.lead import Lead
from app.models.message import Message, MessageEvent
from app.models.outreach import ConnectedAccount
from app.services import suppression
from app.services.email import factory
from app.utils.normalize import normalize_email

logger = logging.getLogger(__name__)

_MAILER_DAEMON_HINTS = ("mailer-daemon", "postmaster", "mail delivery subsystem", "maildelivery")


@dataclass
class InboundEmail:
    message_id: str | None
    from_address: str
    to_addresses: list[str]
    subject: str
    in_reply_to: str | None
    references: list[str]
    body_snippet: str
    is_bounce: bool = False
    bounced_recipient: str | None = None
    raw_headers: dict[str, str] = field(default_factory=dict)


# ---- Pure parsing / classification ----

def _body_text(msg: PyEmailMessage, limit: int = 2000) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace"
                    )[:limit]
                except Exception:  # noqa: BLE001
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", "replace"
        )[:limit]
    except Exception:  # noqa: BLE001
        return ""


def _extract_bounced_recipient(msg: PyEmailMessage) -> str | None:
    """From a DSN (multipart/report; report-type=delivery-status) pull the failed rcpt."""
    for part in msg.walk():
        if part.get_content_type() == "message/delivery-status":
            payload = part.get_payload()
            blocks = payload if isinstance(payload, list) else [part]
            for blk in blocks:
                try:
                    final = blk.get("Final-Recipient") or blk.get("Original-Recipient")
                except Exception:  # noqa: BLE001
                    final = None
                if final:
                    # "rfc822; user@example.com"
                    return normalize_email(final.split(";")[-1].strip())
    return None


def classify(msg: PyEmailMessage) -> tuple[bool, str | None]:
    """Return (is_bounce, bounced_recipient)."""
    from_hdr = (msg.get("From") or "").lower()
    ctype = (msg.get_content_type() or "").lower()
    report_type = (msg.get_param("report-type") or "").lower() if msg.get("Content-Type") else ""
    looks_daemon = any(h in from_hdr for h in _MAILER_DAEMON_HINTS)
    is_dsn = ctype == "multipart/report" or report_type == "delivery-status"
    if is_dsn or looks_daemon:
        return True, _extract_bounced_recipient(msg)
    return False, None


def parse_raw_email(raw: bytes) -> InboundEmail:
    msg = email.message_from_bytes(raw)
    from_address = normalize_email(parseaddr(msg.get("From", ""))[1]) or ""
    tos = [normalize_email(a) or a for _, a in getaddresses(msg.get_all("To", []))]
    refs = (msg.get("References", "") or "").split()
    is_bounce, bounced = classify(msg)
    return InboundEmail(
        message_id=(msg.get("Message-ID") or "").strip() or None,
        from_address=from_address,
        to_addresses=[t for t in tos if t],
        subject=msg.get("Subject", "") or "",
        in_reply_to=(msg.get("In-Reply-To") or "").strip() or None,
        references=refs,
        body_snippet=_body_text(msg),
        is_bounce=is_bounce,
        bounced_recipient=bounced,
    )


# ---- DB matching / recording ----

def _already_stored(db: Session, workspace_id: str, rfc_id: str | None) -> bool:
    if not rfc_id:
        return False
    return db.execute(
        select(Message.id).where(
            Message.workspace_id == workspace_id,
            Message.rfc_message_id == rfc_id,
            Message.direction == MessageDirection.inbound,
        ).limit(1)
    ).first() is not None


def _find_outbound_by_rfc(db: Session, workspace_id: str, rfc_ids: list[str]) -> Message | None:
    rfc_ids = [r for r in rfc_ids if r]
    if not rfc_ids:
        return None
    return db.execute(
        select(Message).where(
            Message.workspace_id == workspace_id,
            Message.direction == MessageDirection.outbound,
            Message.rfc_message_id.in_(rfc_ids),
        ).order_by(Message.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def _latest_outbound_to(db: Session, workspace_id: str, address: str) -> Message | None:
    return db.execute(
        select(Message).where(
            Message.workspace_id == workspace_id,
            Message.direction == MessageDirection.outbound,
            Message.channel == Channel.email,
            Message.to_address == address,
        ).order_by(Message.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def record_reply(db: Session, account: ConnectedAccount, inbound: InboundEmail) -> str:
    ws = account.workspace_id
    thread_ids = ([inbound.in_reply_to] if inbound.in_reply_to else []) + inbound.references
    origin = _find_outbound_by_rfc(db, ws, thread_ids)

    lead = None
    if inbound.from_address:
        lead = db.execute(
            select(Lead).where(Lead.workspace_id == ws, Lead.email == inbound.from_address).limit(1)
        ).scalar_one_or_none()
    # Fallback when RFC threading misses: providers that don't preserve our RFC
    # Message-ID (e.g. Microsoft Graph assigns its own internetMessageId on send)
    # produce replies we can't thread. Match the most recent outbound email to the
    # sender's address — same heuristic the bounce path uses — so campaign linkage
    # (and sequence halting) still works.
    if origin is None and inbound.from_address:
        origin = _latest_outbound_to(db, ws, inbound.from_address)
    if lead is None and origin is not None and origin.lead_id:
        lead = db.get(Lead, origin.lead_id)
    if lead is None and origin is None:
        return "reply_unmatched"
    if lead is None and origin is None:
        return "reply_unmatched"

    campaign_id = origin.campaign_id if origin else None
    campaign_lead_id = origin.campaign_lead_id if origin else None

    inbound_msg = Message(
        workspace_id=ws,
        lead_id=lead.id if lead else None,
        campaign_id=campaign_id,
        campaign_lead_id=campaign_lead_id,
        channel=Channel.email,
        direction=MessageDirection.inbound,
        status=MessageStatus.replied,
        subject=inbound.subject,
        body=inbound.body_snippet,
        to_address=account.external_id,
        provider_message_id=inbound.message_id,
        rfc_message_id=inbound.message_id,
        meta={"from_address": inbound.from_address},
    )
    db.add(inbound_msg)
    db.flush()
    db.add(MessageEvent(
        workspace_id=ws, message_id=(origin.id if origin else inbound_msg.id),
        type=MessageEventType.replied, provenance=Provenance.observed,
        detail={"from": inbound.from_address, "subject": inbound.subject},
    ))

    # Halt the sequence for this member.
    if campaign_lead_id:
        member = db.get(CampaignLead, campaign_lead_id)
        if member and member.state in (CampaignLeadState.active, CampaignLeadState.pending):
            member.state = CampaignLeadState.replied
            member.next_action_at = None
            member.last_reason = "replied"
    if lead:
        lead.status = LeadStatus.replied

    # AI reply classification (Phase 4). Never blocks reply handling — any failure or a
    # disabled AIService just leaves the reply unclassified. An "unsubscribe" intent is
    # honored by adding the sender to the suppression list.
    _classify_and_annotate(db, ws, inbound_msg, inbound)
    return "reply_recorded"


def _classify_and_annotate(db: Session, ws: str, inbound_msg: Message, inbound: InboundEmail) -> None:
    try:
        from app.services.ai import log as ai_log
        from app.services.ai.factory import get_ai_service

        svc = get_ai_service()
        if not svc.enabled:
            return
        res = svc.classify_reply(inbound.body_snippet or inbound.subject or "")
        ai_log.record(db, res, workspace_id=ws, lead_id=inbound_msg.lead_id,
                      message_id=inbound_msg.id)
        if not res.ok:
            return
        intent = res.output.get("intent")
        meta = dict(inbound_msg.meta or {})
        meta["ai_intent"] = intent
        meta["ai_sentiment"] = res.output.get("sentiment")
        inbound_msg.meta = meta
        if intent == "unsubscribe" and inbound.from_address:
            suppression.add_suppression(
                db, ws, "email", inbound.from_address,
                SuppressionReason.unsubscribed, note="AI-classified unsubscribe reply",
            )
    except Exception:  # noqa: BLE001 — classification is best-effort
        logger.warning("Reply classification failed", exc_info=True)


def record_bounce(db: Session, account: ConnectedAccount, inbound: InboundEmail) -> str:
    ws = account.workspace_id
    rcpt = inbound.bounced_recipient
    if not rcpt:
        return "bounce_no_recipient"
    origin = _latest_outbound_to(db, ws, rcpt)

    suppression.add_suppression(
        db, ws, "email", rcpt, SuppressionReason.bounced, note="Bounce (DSN)"
    )
    if origin:
        origin.status = MessageStatus.bounced
        db.add(MessageEvent(
            workspace_id=ws, message_id=origin.id, type=MessageEventType.bounced,
            provenance=Provenance.observed, detail={"recipient": rcpt},
        ))
        if origin.campaign_lead_id:
            member = db.get(CampaignLead, origin.campaign_lead_id)
            if member and member.state in (CampaignLeadState.active, CampaignLeadState.pending):
                member.state = CampaignLeadState.bounced
                member.next_action_at = None
                member.last_reason = "bounced"
    return "bounce_recorded"


def record_inbound(db: Session, account: ConnectedAccount, inbound: InboundEmail) -> str:
    if _already_stored(db, account.workspace_id, inbound.message_id):
        return "duplicate"
    if inbound.is_bounce:
        return record_bounce(db, account, inbound)
    return record_reply(db, account, inbound)


# ---- Provider fetch ----

def _fetch_imap(creds: dict) -> list[InboundEmail]:
    # Require an explicitly configured IMAP host — an SMTP host rarely also serves IMAP,
    # so we never guess one (guessing caused failed connects on send-only accounts).
    host = creds.get("imap_host")
    if not host:
        return []
    use_ssl = creds.get("imap_ssl", True)
    port = int(creds.get("imap_port") or (993 if use_ssl else 143))
    user = creds.get("imap_username") or creds.get("username")
    pw = creds.get("imap_password") or creds.get("password")
    out: list[InboundEmail] = []
    M = None
    try:
        M = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        if user:
            M.login(user, pw or "")
        M.select("INBOX")
        since = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%d-%b-%Y")
        typ, data = M.search(None, f"(SINCE {since})")
        ids = data[0].split() if data and data[0] else []
        for num in ids[-100:]:
            typ, msg_data = M.fetch(num, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if isinstance(raw, bytes):
                out.append(parse_raw_email(raw))
    except Exception as exc:  # noqa: BLE001 — unreachable/auth-failed mailbox shouldn't 500
        logger.warning("IMAP poll failed for %s:%s — %s", host, port, exc)
    finally:
        if M is not None:
            try:
                M.logout()
            except Exception:  # noqa: BLE001
                pass
    return out


def _fetch_gmail(access_token: str) -> list[InboundEmail]:
    headers = {"Authorization": f"Bearer {access_token}"}
    out: list[InboundEmail] = []
    try:
        listing = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers, params={"q": "newer_than:3d -from:me", "maxResults": 50}, timeout=30,
        )
        listing.raise_for_status()
        for m in listing.json().get("messages", []):
            g = httpx.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}",
                headers=headers, params={"format": "raw"}, timeout=30,
            )
            if g.status_code >= 400:
                continue
            raw = base64.urlsafe_b64decode(g.json().get("raw", ""))
            out.append(parse_raw_email(raw))
    except httpx.HTTPError as exc:
        logger.warning("Gmail poll failed: %s", exc)
    return out


def _fetch_microsoft(access_token: str) -> list[InboundEmail]:
    headers = {"Authorization": f"Bearer {access_token}"}
    out: list[InboundEmail] = []
    try:
        listing = httpx.get(
            "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
            headers=headers, params={"$top": 50, "$orderby": "receivedDateTime desc"}, timeout=30,
        )
        listing.raise_for_status()
        for m in listing.json().get("value", []):
            mime = httpx.get(
                f"https://graph.microsoft.com/v1.0/me/messages/{m['id']}/$value",
                headers=headers, timeout=30,
            )
            if mime.status_code >= 400:
                continue
            out.append(parse_raw_email(mime.content))
    except httpx.HTTPError as exc:
        logger.warning("Graph poll failed: %s", exc)
    return out


def poll_account(db: Session, account: ConnectedAccount) -> dict:
    try:
        creds = factory.fresh_credentials(db, account)
        if account.provider == "smtp":
            messages = _fetch_imap(creds)
        elif account.provider == "gmail":
            messages = _fetch_gmail(creds.get("access_token", ""))
        elif account.provider == "microsoft":
            messages = _fetch_microsoft(creds.get("access_token", ""))
        else:
            return {}
    except Exception:  # noqa: BLE001 — a fetch/creds failure yields no messages, never a 500
        logger.exception("Fetch failed for account %s (%s)", account.id, account.provider)
        return {"fetch_error": 1}
    outcomes: dict[str, int] = {}
    for inbound in messages:
        try:
            outcome = record_inbound(db, account, inbound)
        except Exception:  # noqa: BLE001 — one bad message shouldn't abort the poll
            logger.exception("Failed to record inbound message")
            outcome = "error"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return outcomes


def poll_all(db: Session) -> dict:
    from app.models.enums import ConnectedAccountStatus, ConnectedAccountType

    accounts = db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.type == ConnectedAccountType.email,
            ConnectedAccount.status == ConnectedAccountStatus.connected,
        )
    ).scalars().all()
    totals: dict[str, int] = {}
    for account in accounts:
        try:
            for k, v in poll_account(db, account).items():
                totals[k] = totals.get(k, 0) + v
        except Exception:  # noqa: BLE001
            logger.exception("Poll failed for account %s", account.id)
    db.commit()
    return totals
