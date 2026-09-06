"""Phase 6 — WhatsApp via the OpenWA microservice. The service HTTP boundary is
stubbed (``app.services.whatsapp.client``) so these run hermetically: they cover
the live send path through WhatsAppProvider, send-failure retry, the account gate,
session reconcile, and the inbound webhook (auth + sequence halt)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.campaign import CampaignLead
from app.models.enums import CampaignLeadState, MessageDirection, MessageStatus
from app.models.message import Message
from app.services import engine
from app.services.whatsapp import client as wa_client
from tests.conftest import auth_headers, requires_db, signup

TOKEN = "test-wa-token"


@pytest.fixture(autouse=True)
def _wa_token(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "WHATSAPP_SERVICE_TOKEN", TOKEN)


def _wa_lead(client, h, name="Sam Fox", phone="+15551234567"):
    r = client.post("/api/v1/leads", headers=h, json={"full_name": name, "phone": phone})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _campaign(client, h, *, test_mode: bool, delay: int = 0):
    body = {
        "name": "WA Outreach", "test_mode": test_mode, "approval_mode": "auto",
        "channels": {"whatsapp": {"enabled": True}},
        "steps": [{"channel": "whatsapp", "delay_days": delay,
                   "body_template": "Hi {{first_name}}, following up here."}],
    }
    r = client.post("/api/v1/campaigns", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _launch(client, h, cid, phone="+15551234567"):
    lid = _wa_lead(client, h, phone=phone)
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": [lid]})
    assert client.post(f"/api/v1/campaigns/{cid}/launch", headers=h).status_code == 200
    return lid


def _connect(client, h, monkeypatch, me="15550000000"):
    monkeypatch.setattr(wa_client, "session_start",
                        lambda: {"status": "connected", "qr": None, "me": me, "mode": "mock"})
    r = client.post("/api/v1/whatsapp/connect", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


@requires_db
def test_connect_reconciles_account(client, monkeypatch):
    token, ws = signup(client, email="wa-connect@example.com")
    h = auth_headers(token, ws)
    out = _connect(client, h, monkeypatch)
    assert out["status"] == "connected" and out["me"] == "15550000000"
    assert out["account_id"]
    # Gate now sees a connected whatsapp account.
    lid = _wa_lead(client, h)
    cid = _campaign(client, h, test_mode=False)
    r = client.post(f"/api/v1/campaigns/{cid}/preview-send", headers=h,
                    json={"lead_id": lid, "channel": "whatsapp"})
    assert r.json()["checks"]["account_connected"] is True


@requires_db
def test_live_send_through_provider(client, db, monkeypatch):
    token, ws = signup(client, email="wa-send@example.com")
    h = auth_headers(token, ws)
    _connect(client, h, monkeypatch)
    sent: list = []
    monkeypatch.setattr(wa_client, "send",
                        lambda to, body: sent.append((to, body)) or {"success": True, "id": "wamid.ABC"})

    cid = _campaign(client, h, test_mode=False)
    _launch(client, h, cid)
    engine.tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))

    assert sent and sent[0][0] == "+15551234567" and "Hi Sam" in sent[0][1]
    msg = db.execute(
        select(Message).where(Message.campaign_id == cid,
                              Message.direction == MessageDirection.outbound)
    ).scalar_one()
    assert msg.status == MessageStatus.sent
    assert msg.provider_message_id == "wamid.ABC"
    member = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalar_one()
    assert member.state == CampaignLeadState.completed


@requires_db
def test_send_failure_retries(client, db, monkeypatch):
    token, ws = signup(client, email="wa-fail@example.com")
    h = auth_headers(token, ws)
    _connect(client, h, monkeypatch)

    def _boom(to, body):
        raise wa_client.WhatsAppServiceError("service down")
    monkeypatch.setattr(wa_client, "send", _boom)

    cid = _campaign(client, h, test_mode=False)
    _launch(client, h, cid)
    engine.tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))

    msg = db.execute(
        select(Message).where(Message.campaign_id == cid,
                              Message.direction == MessageDirection.outbound)
    ).scalar_one()
    assert msg.status == MessageStatus.failed
    member = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalar_one()
    # Transient failure → still active, retry scheduled, step not advanced.
    assert member.state == CampaignLeadState.active
    assert member.current_step == 0
    assert member.next_action_at is not None


@requires_db
def test_test_mode_simulates(client, db, monkeypatch):
    token, ws = signup(client, email="wa-sim@example.com")
    h = auth_headers(token, ws)

    def _fail(*a, **k):
        raise AssertionError("provider must not be called in test mode")
    monkeypatch.setattr(wa_client, "send", _fail)

    cid = _campaign(client, h, test_mode=True)  # no connected account needed
    _launch(client, h, cid)
    engine.tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))

    msg = db.execute(
        select(Message).where(Message.campaign_id == cid,
                              Message.direction == MessageDirection.outbound)
    ).scalar_one()
    assert msg.status == MessageStatus.simulated


@requires_db
def test_webhook_records_reply_and_halts(client, db, monkeypatch):
    token, ws = signup(client, email="wa-reply@example.com")
    h = auth_headers(token, ws)
    _connect(client, h, monkeypatch)
    monkeypatch.setattr(wa_client, "send", lambda to, body: {"success": True, "id": "wamid.OUT"})
    cid = _campaign(client, h, test_mode=False)
    _launch(client, h, cid)
    engine.tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))

    # Inbound reply from the lead's number (WhatsApp JID form).
    r = client.post("/api/v1/whatsapp/webhook",
                    headers={"X-Service-Token": TOKEN},
                    json={"from": "15551234567@c.us", "body": "Yes, interested!", "provider_message_id": "wamid.IN"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    member = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalar_one()
    assert member.state == CampaignLeadState.replied
    inbound = db.execute(
        select(Message).where(Message.campaign_id == cid,
                              Message.direction == MessageDirection.inbound)
    ).scalar_one()
    assert inbound.body == "Yes, interested!"
    inbox = client.get("/api/v1/inbox", headers=h).json()
    assert any(i["channel"] == "whatsapp" for i in inbox)


@requires_db
def test_webhook_rejects_bad_token(client):
    r = client.post("/api/v1/whatsapp/webhook",
                    headers={"X-Service-Token": "wrong"},
                    json={"from": "15551234567@c.us", "body": "hi"})
    assert r.status_code == 401
