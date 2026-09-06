"""Phase 5 — assisted LinkedIn. Covers the identity/account gate, engine parking of
live LinkedIn sends into manual tasks, the task queue (complete/skip), manual reply
logging (sequence halt), and that test-mode LinkedIn still simulates (no parking).

DB-backed: exercises the engine + API against the test database."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.campaign import CampaignLead
from app.models.enums import CampaignLeadState, MessageDirection, MessageStatus
from app.models.message import Message
from app.services import engine
from tests.conftest import auth_headers, requires_db, signup


def _linkedin_lead(client, h, name="Dana Lee", url="https://linkedin.com/in/danalee"):
    r = client.post("/api/v1/leads", headers=h, json={
        "full_name": name, "title": "VP Sales", "linkedin_url": url,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _campaign(client, h, *, test_mode: bool, delay: int = 0):
    body = {
        "name": "LI Outreach",
        "test_mode": test_mode,
        "approval_mode": "auto",
        "channels": {"linkedin": {"enabled": True}},
        "steps": [
            {"channel": "linkedin", "delay_days": delay,
             "body_template": "Hi {{first_name}}, quick question about {{title}}."},
        ],
    }
    r = client.post("/api/v1/campaigns", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _launch_with_lead(client, h, cid):
    lid = _linkedin_lead(client, h)
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": [lid]})
    r = client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)
    assert r.status_code == 200, r.text
    return lid


@requires_db
def test_connect_and_list_identity(client):
    token, ws = signup(client, email="li-connect@example.com")
    h = auth_headers(token, ws)
    r = client.post("/api/v1/linkedin/account", headers=h,
                    json={"display_name": "Sales Rep", "profile_url": "https://linkedin.com/in/rep"})
    assert r.status_code == 201, r.text
    assert r.json()["provider"] == "assisted"
    listing = client.get("/api/v1/linkedin/account", headers=h).json()
    assert len(listing) == 1 and listing[0]["display_name"] == "Sales Rep"


@requires_db
def test_live_linkedin_requires_connected_identity(client):
    token, ws = signup(client, email="li-gate@example.com")
    h = auth_headers(token, ws)
    cid = _campaign(client, h, test_mode=False)
    lid = _linkedin_lead(client, h)
    # No identity connected yet → account_connected fails.
    r = client.post(f"/api/v1/campaigns/{cid}/preview-send", headers=h,
                    json={"lead_id": lid, "channel": "linkedin"})
    assert r.status_code == 200
    assert r.json()["allowed"] is False
    assert r.json()["checks"]["account_connected"] is False

    client.post("/api/v1/linkedin/account", headers=h, json={"display_name": "Rep"})
    r = client.post(f"/api/v1/campaigns/{cid}/preview-send", headers=h,
                    json={"lead_id": lid, "channel": "linkedin"})
    assert r.json()["checks"]["account_connected"] is True
    assert r.json()["allowed"] is True


@requires_db
def test_engine_parks_live_send_as_task(client, db):
    token, ws = signup(client, email="li-park@example.com")
    h = auth_headers(token, ws)
    client.post("/api/v1/linkedin/account", headers=h, json={"display_name": "Rep"})
    cid = _campaign(client, h, test_mode=False)
    _launch_with_lead(client, h, cid)

    engine.tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))

    member = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalar_one()
    assert member.state == CampaignLeadState.awaiting_action
    assert member.next_action_at is None

    msg = db.execute(
        select(Message).where(Message.campaign_id == cid,
                              Message.direction == MessageDirection.outbound)
    ).scalar_one()
    assert msg.status == MessageStatus.pending_action
    assert "Hi Dana" in (msg.body or "")  # template rendered

    # Task queue surfaces it via the API.
    tasks = client.get("/api/v1/linkedin/tasks", headers=h).json()
    assert len(tasks) == 1
    assert tasks[0]["profile_url"] == "https://linkedin.com/in/danalee"
    assert tasks[0]["id"] == msg.id


@requires_db
def test_complete_task_advances_and_completes(client, db):
    token, ws = signup(client, email="li-complete@example.com")
    h = auth_headers(token, ws)
    client.post("/api/v1/linkedin/account", headers=h, json={"display_name": "Rep"})
    cid = _campaign(client, h, test_mode=False)
    _launch_with_lead(client, h, cid)
    engine.tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))

    task_id = client.get("/api/v1/linkedin/tasks", headers=h).json()[0]["id"]
    r = client.post(f"/api/v1/linkedin/tasks/{task_id}/complete", headers=h, json={"note": "sent"})
    assert r.status_code == 200, r.text

    db.expire_all()
    msg = db.get(Message, task_id)
    assert msg.status == MessageStatus.sent
    member = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalar_one()
    # Single-step sequence → member completes after the one send is confirmed.
    assert member.state == CampaignLeadState.completed
    assert member.current_step == 1

    # Task no longer open → completing again is a 409.
    r2 = client.post(f"/api/v1/linkedin/tasks/{task_id}/complete", headers=h)
    assert r2.status_code == 409
    assert client.get("/api/v1/linkedin/tasks", headers=h).json() == []


@requires_db
def test_skip_task_advances_past_step(client, db):
    token, ws = signup(client, email="li-skip@example.com")
    h = auth_headers(token, ws)
    client.post("/api/v1/linkedin/account", headers=h, json={"display_name": "Rep"})
    cid = _campaign(client, h, test_mode=False)
    _launch_with_lead(client, h, cid)
    engine.tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))

    task_id = client.get("/api/v1/linkedin/tasks", headers=h).json()[0]["id"]
    r = client.post(f"/api/v1/linkedin/tasks/{task_id}/skip", headers=h, json={"reason": "no profile"})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(Message, task_id).status == MessageStatus.failed
    member = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalar_one()
    assert member.current_step == 1
    assert member.state == CampaignLeadState.completed


@requires_db
def test_log_reply_halts_sequence(client, db):
    token, ws = signup(client, email="li-reply@example.com")
    h = auth_headers(token, ws)
    client.post("/api/v1/linkedin/account", headers=h, json={"display_name": "Rep"})
    cid = _campaign(client, h, test_mode=False)
    _launch_with_lead(client, h, cid)
    engine.tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))
    task_id = client.get("/api/v1/linkedin/tasks", headers=h).json()[0]["id"]
    client.post(f"/api/v1/linkedin/tasks/{task_id}/complete", headers=h)

    r = client.post(f"/api/v1/linkedin/tasks/{task_id}/reply", headers=h,
                    json={"text": "Sure, tell me more!", "from_name": "Dana Lee"})
    assert r.status_code == 200, r.text

    db.expire_all()
    member = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalar_one()
    assert member.state == CampaignLeadState.replied
    inbound = db.execute(
        select(Message).where(Message.campaign_id == cid,
                              Message.direction == MessageDirection.inbound)
    ).scalar_one()
    assert inbound.body == "Sure, tell me more!"
    # Shows up in the workspace inbox.
    inbox = client.get("/api/v1/inbox", headers=h).json()
    assert any(i["channel"] == "linkedin" for i in inbox)


@requires_db
def test_test_mode_linkedin_simulates_no_parking(client, db):
    token, ws = signup(client, email="li-sim@example.com")
    h = auth_headers(token, ws)
    cid = _campaign(client, h, test_mode=True)  # no identity needed in test mode
    _launch_with_lead(client, h, cid)
    engine.tick(db, now=datetime.now(timezone.utc) + timedelta(minutes=1))

    member = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalar_one()
    assert member.state == CampaignLeadState.completed  # simulated send advanced it
    msg = db.execute(
        select(Message).where(Message.campaign_id == cid,
                              Message.direction == MessageDirection.outbound)
    ).scalar_one()
    assert msg.status == MessageStatus.simulated
    assert client.get("/api/v1/linkedin/tasks", headers=h).json() == []
