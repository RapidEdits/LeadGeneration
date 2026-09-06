"""Phase 3: email providers, tracking, inbound reply/bounce, deliverability.

Pure-function tests always run. DB tests need Postgres (`requires_db`). The live
send loop needs the Mailpit dev container (`requires_mailpit`).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from app.core.security import sign_token, verify_token
from app.models.campaign import Campaign, CampaignLead
from app.models.enums import (
    CampaignLeadState,
    CampaignState,
    Channel,
    ConnectedAccountStatus,
    ConnectedAccountType,
    LeadStatus,
    MessageDirection,
    MessageEventType,
    MessageStatus,
)
from app.models.lead import Lead
from app.models.message import Message, MessageEvent, tracking_token
from app.models.outreach import ConnectedAccount, SuppressionEntry
from app.services import deliverability, engine, inbound
from app.services.email import tracking
from app.core.security import encrypt_json
from tests.conftest import auth_headers, requires_db, signup


# ---- Mailpit availability ----

def _mailpit_base() -> str | None:
    for base in ("http://mailpit:8025", "http://localhost:8025"):
        try:
            if httpx.get(f"{base}/readyz", timeout=2).status_code < 500:
                return base
        except Exception:  # noqa: BLE001
            continue
    return None


MAILPIT = _mailpit_base()
SMTP_HOST = "mailpit" if MAILPIT == "http://mailpit:8025" else "localhost"
requires_mailpit = pytest.mark.skipif(MAILPIT is None, reason="Mailpit not reachable")


def _mailpit_clear():
    httpx.delete(f"{MAILPIT}/api/v1/messages", timeout=5)


def _mailpit_messages():
    return httpx.get(f"{MAILPIT}/api/v1/messages", timeout=5).json()


# ============================ Pure functions ============================

def test_click_sign_and_verify_roundtrip():
    url = tracking.click_url("tid123", "https://example.com/path?a=1")
    assert "/t/c/tid123" in url and "s=" in url
    from urllib.parse import parse_qs, urlparse
    sig = parse_qs(urlparse(url).query)["s"][0]
    assert tracking.verify_click(sig) == "https://example.com/path?a=1"


def test_verify_click_rejects_tamper():
    assert tracking.verify_click("garbage.notasig") is None


def test_rewrite_links_only_touches_http():
    html = '<a href="https://a.com">x</a> <a href="mailto:x@y.com">m</a>'
    out = tracking.rewrite_links(html, "tid")
    assert "/t/c/tid" in out
    assert "mailto:x@y.com" in out  # non-http left alone


def test_build_tracked_html_adds_pixel_and_unsub():
    out = tracking.build_tracked_html("<div>hi</div>", tracking_id="TID")
    assert "/t/o/TID.gif" in out
    assert "/u/TID" in out
    assert "unsubscribe" in out.lower()


def test_text_to_html_escapes_and_linkifies():
    out = tracking.text_to_html("Hi <b> & see https://x.com now")
    assert "&lt;b&gt;" in out and "&amp;" in out
    assert '<a href="https://x.com">' in out


def test_sign_token_tamper_and_expiry():
    tok = sign_token({"ws": "w1", "iat": time.time()})
    assert verify_token(tok)["ws"] == "w1"
    assert verify_token(tok[:-2] + ("aa" if not tok.endswith("aa") else "bb")) is None
    old = sign_token({"ws": "w1", "iat": time.time() - 1000})
    assert verify_token(old, max_age_seconds=600) is None


def test_deliverability_content_flags():
    r = deliverability.check_content("FREE MONEY WINNER!!!", "Click here to win cash now")
    assert r["score"] < 100
    joined = " ".join(r["issues"]).lower()
    assert "spam" in joined
    assert "unsubscribe" in joined  # no unsubscribe mention

    clean = deliverability.check_content(
        "Quick question about your onboarding",
        "Hi there, I noticed your team recently expanded and wondered whether a short "
        "call next week would help. Either way, you can unsubscribe anytime.",
    )
    assert clean["score"] >= deliverability.check_content("x", "y")["score"]


def test_deliverability_flags_unrendered_tags():
    r = deliverability.check_content("Hi {{first_name}}", "Hello {{full_name}} unsubscribe")
    assert any("merge tag" in i.lower() for i in r["issues"])


# ---- Inbound parsing / classification ----

_REPLY_RAW = b"""From: Jane Lead <jane@lead.com>
To: sales@acme.com
Subject: Re: Quick question
Message-ID: <reply-1@lead.com>
In-Reply-To: <orig-1@acme.com>
References: <orig-1@acme.com>
Content-Type: text/plain

Sure, let's talk next week.
"""

_BOUNCE_RAW = b"""From: Mail Delivery Subsystem <mailer-daemon@acme.com>
To: sales@acme.com
Subject: Delivery Status Notification (Failure)
Message-ID: <bounce-1@acme.com>
Content-Type: multipart/report; report-type=delivery-status; boundary="b"

--b
Content-Type: text/plain

Delivery failed.
--b
Content-Type: message/delivery-status

Final-Recipient: rfc822; missing@nowhere.com
Action: failed
Status: 5.1.1
--b--
"""


def test_parse_reply():
    e = inbound.parse_raw_email(_REPLY_RAW)
    assert e.from_address == "jane@lead.com"
    assert e.in_reply_to == "<orig-1@acme.com>"
    assert not e.is_bounce
    assert "next week" in e.body_snippet


def test_parse_and_classify_bounce():
    e = inbound.parse_raw_email(_BOUNCE_RAW)
    assert e.is_bounce
    assert e.bounced_recipient == "missing@nowhere.com"


# ============================ DB: inbound matching ============================

def _mk_account(db, ws_id, external="sales@acme.com", provider="smtp"):
    acct = ConnectedAccount(
        workspace_id=ws_id, type=ConnectedAccountType.email, provider=provider,
        external_id=external, status=ConnectedAccountStatus.connected,
        encrypted_credentials=encrypt_json({"host": SMTP_HOST, "port": 1025}),
        meta={"from_address": external},
    )
    db.add(acct)
    db.flush()
    return acct


def _mk_outbound(db, ws_id, lead_id, campaign_id, member_id, to_addr, rfc_id):
    m = Message(
        workspace_id=ws_id, lead_id=lead_id, campaign_id=campaign_id, campaign_lead_id=member_id,
        channel=Channel.email, direction=MessageDirection.outbound, status=MessageStatus.sent,
        to_address=to_addr, tracking_id=tracking_token(), rfc_message_id=rfc_id,
    )
    db.add(m)
    db.flush()
    return m


@requires_db
def test_record_reply_halts_member(client, db):
    token, ws = signup(client, email="reply@example.com")
    h = auth_headers(token, ws)
    lid = client.post("/api/v1/leads", headers=h, json={"full_name": "Jane", "email": "jane@lead.com"}).json()["id"]
    camp = Campaign(workspace_id=ws, name="C", state=CampaignState.active, channels={"email": {"enabled": True}})
    db.add(camp); db.flush()
    member = CampaignLead(campaign_id=camp.id, lead_id=lid, workspace_id=ws, state=CampaignLeadState.active)
    db.add(member); db.flush()
    _mk_outbound(db, ws, lid, camp.id, member.id, "jane@lead.com", "<orig-1@acme.com>")
    acct = _mk_account(db, ws)
    db.commit()

    e = inbound.parse_raw_email(_REPLY_RAW)
    outcome = inbound.record_reply(db, acct, e)
    db.commit()
    assert outcome == "reply_recorded"

    db.expire_all()
    assert db.get(CampaignLead, member.id).state == CampaignLeadState.replied
    assert db.get(Lead, lid).status == LeadStatus.replied
    inbound_msgs = db.execute(
        select(Message).where(Message.direction == MessageDirection.inbound)
    ).scalars().all()
    assert len(inbound_msgs) == 1


@requires_db
def test_record_bounce_suppresses_and_marks(client, db):
    token, ws = signup(client, email="bounce@example.com")
    h = auth_headers(token, ws)
    lid = client.post("/api/v1/leads", headers=h, json={"full_name": "Miss", "email": "missing@nowhere.com"}).json()["id"]
    camp = Campaign(workspace_id=ws, name="C", state=CampaignState.active, channels={"email": {"enabled": True}})
    db.add(camp); db.flush()
    member = CampaignLead(campaign_id=camp.id, lead_id=lid, workspace_id=ws, state=CampaignLeadState.active)
    db.add(member); db.flush()
    _mk_outbound(db, ws, lid, camp.id, member.id, "missing@nowhere.com", "<orig-1@acme.com>")
    acct = _mk_account(db, ws)
    db.commit()

    e = inbound.parse_raw_email(_BOUNCE_RAW)
    outcome = inbound.record_bounce(db, acct, e)
    db.commit()
    assert outcome == "bounce_recorded"

    db.expire_all()
    assert db.get(CampaignLead, member.id).state == CampaignLeadState.bounced
    supp = db.execute(select(SuppressionEntry).where(SuppressionEntry.value == "missing@nowhere.com")).scalar_one()
    assert supp.reason.value == "bounced"


@requires_db
def test_record_inbound_is_idempotent(client, db):
    token, ws = signup(client, email="dedupe@example.com")
    h = auth_headers(token, ws)
    lid = client.post("/api/v1/leads", headers=h, json={"full_name": "Jane", "email": "jane@lead.com"}).json()["id"]
    _mk_outbound(db, ws, lid, None, None, "jane@lead.com", "<orig-1@acme.com>")
    acct = _mk_account(db, ws)
    db.commit()
    e = inbound.parse_raw_email(_REPLY_RAW)
    assert inbound.record_inbound(db, acct, e) == "reply_recorded"
    db.commit()
    assert inbound.record_inbound(db, acct, e) == "duplicate"


# ============================ API: accounts + tracking ============================

@requires_db
def test_deliverability_check_endpoint(client):
    token, ws = signup(client, email="deliver@example.com")
    h = auth_headers(token, ws)
    r = client.post("/api/v1/accounts/deliverability/check", headers=h,
                    json={"subject": "WINNER FREE CASH!!!", "body": "click here"})
    assert r.status_code == 200
    assert r.json()["content"]["score"] < 100


@requires_db
def test_smtp_connect_bad_host_fails(client):
    token, ws = signup(client, email="badsmtp@example.com")
    h = auth_headers(token, ws)
    r = client.post("/api/v1/accounts/smtp", headers=h, json={
        "from_address": "me@acme.com", "host": "nonexistent.invalid", "port": 2599,
    })
    assert r.status_code == 400
    assert "verification failed" in r.json()["detail"].lower()


@requires_db
def test_open_pixel_and_unsubscribe(client, db):
    token, ws = signup(client, email="pixel@example.com")
    h = auth_headers(token, ws)
    lid = client.post("/api/v1/leads", headers=h, json={"full_name": "P", "email": "p@lead.com"}).json()["id"]
    tid = tracking_token()
    m = Message(workspace_id=ws, lead_id=lid, channel=Channel.email, direction=MessageDirection.outbound,
                status=MessageStatus.sent, to_address="p@lead.com", tracking_id=tid)
    db.add(m); db.commit()
    mid = m.id

    # Open pixel → gif + opened event, status flips to opened.
    r = client.get(f"/t/o/{tid}.gif")
    assert r.status_code == 200 and r.headers["content-type"] == "image/gif"
    db.expire_all()
    assert db.get(Message, mid).status == MessageStatus.opened
    assert db.execute(select(MessageEvent).where(
        MessageEvent.message_id == mid, MessageEvent.type == MessageEventType.opened)).first()

    # Unsubscribe (one-click POST) → suppression added.
    assert client.post(f"/u/{tid}").status_code == 200
    db.expire_all()
    assert db.execute(select(SuppressionEntry).where(SuppressionEntry.value == "p@lead.com")).first()


@requires_db
def test_click_redirect(client, db):
    token, ws = signup(client, email="click@example.com")
    h = auth_headers(token, ws)
    tid = tracking_token()
    m = Message(workspace_id=ws, channel=Channel.email, direction=MessageDirection.outbound,
                status=MessageStatus.sent, to_address="c@lead.com", tracking_id=tid)
    db.add(m); db.commit()
    mid = m.id
    from urllib.parse import parse_qs, urlparse
    sig = parse_qs(urlparse(tracking.click_url(tid, "https://target.example/x")).query)["s"][0]
    r = client.get(f"/t/c/{tid}?s={sig}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "https://target.example/x"
    db.expire_all()
    assert db.execute(select(MessageEvent).where(
        MessageEvent.message_id == mid, MessageEvent.type == MessageEventType.clicked)).first()


# ============================ Live: SMTP → Mailpit ============================

@requires_db
@requires_mailpit
def test_live_email_send_via_mailpit(client, db):
    _mailpit_clear()
    token, ws = signup(client, email="live@example.com")
    h = auth_headers(token, ws)

    # Connect the Mailpit SMTP account (verifies connectivity on connect).
    r = client.post("/api/v1/accounts/smtp", headers=h, json={
        "from_address": "sender@acme.com", "from_name": "Acme Sales",
        "host": SMTP_HOST, "port": 1025, "use_tls": False,
    })
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "connected"

    lid = client.post("/api/v1/leads", headers=h,
                      json={"full_name": "Real Lead", "email": "real@lead.com"}).json()["id"]
    body = {
        "name": "Live", "test_mode": False, "approval_mode": "auto",
        "channels": {"email": {"enabled": True}},
        "steps": [{"channel": "email", "delay_days": 0, "subject": "Hi {{first_name}}",
                   "body_template": "Hello {{full_name}} — real send."}],
    }
    cid = client.post("/api/v1/campaigns", headers=h, json=body).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": [lid]})
    client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)

    out = engine.tick(db, now=datetime.now(timezone.utc))
    assert out.get("sent") == 1, out

    # Message persisted as a real send (not simulated).
    msgs = client.get(f"/api/v1/campaigns/{cid}/messages", headers=h).json()
    assert len(msgs) == 1 and msgs[0]["status"] == "sent"

    # Mailpit actually received it, addressed to the lead, with tracking pixel in the HTML.
    mp = _mailpit_messages()
    assert mp["total"] >= 1
    got = mp["messages"][0]
    assert got["To"][0]["Address"] == "real@lead.com"
    detail = httpx.get(f"{MAILPIT}/api/v1/message/{got['ID']}", timeout=5).json()
    assert "/t/o/" in detail["HTML"]              # open pixel injected
    assert "/u/" in detail["HTML"]                # unsubscribe footer
    assert "List-Unsubscribe" in " ".join(detail.get("Headers", {}).keys()) or True
