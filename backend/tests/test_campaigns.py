"""Phase 2: campaign engine, can_send gate, and state machine (DB-backed)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.campaign import Campaign, CampaignLead
from app.models.enums import CampaignLeadState, CampaignState
from app.services import engine
from app.services.can_send import can_send
from tests.conftest import auth_headers, requires_db, signup


def _make_leads(client, h, emails):
    ids = []
    for i, e in enumerate(emails):
        r = client.post("/api/v1/leads", headers=h, json={"full_name": f"Lead {i}", "email": e})
        ids.append(r.json()["id"])
    return ids


def _campaign_body(name="Q3 Outreach", enabled=True, daily_limit=None, delay=0):
    return {
        "name": name,
        "test_mode": True,
        "approval_mode": "auto",
        "channels": {"email": {"enabled": enabled, "daily_limit": daily_limit}},
        "steps": [
            {"channel": "email", "delay_days": delay, "subject": "Hi {{first_name}}",
             "body_template": "Hello {{full_name}} at step one."},
            {"channel": "email", "delay_days": 0, "subject": "Follow up",
             "body_template": "Following up, {{first_name}}."},
        ],
    }


@requires_db
def test_create_and_get_campaign(client):
    token, ws = signup(client, email="camp@example.com")
    h = auth_headers(token, ws)
    r = client.post("/api/v1/campaigns", headers=h, json=_campaign_body())
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["state"] == "draft"
    assert len(c["steps"]) == 2
    assert c["steps"][0]["order_index"] == 0


@requires_db
def test_launch_requires_leads(client):
    token, ws = signup(client, email="noleads@example.com")
    h = auth_headers(token, ws)
    cid = client.post("/api/v1/campaigns", headers=h, json=_campaign_body()).json()["id"]
    r = client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)
    assert r.status_code == 400  # no leads


@requires_db
def test_full_engine_simulated_send(client, db):
    token, ws = signup(client, email="engine@example.com")
    h = auth_headers(token, ws)
    lead_ids = _make_leads(client, h, ["a@x.com", "b@x.com"])
    cid = client.post("/api/v1/campaigns", headers=h, json=_campaign_body(delay=0)).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": lead_ids})

    r = client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)
    assert r.status_code == 200 and r.json()["state"] == "active"

    # First tick: step 0 sends for both leads.
    now = datetime.now(timezone.utc)
    out1 = engine.tick(db, now=now)
    assert out1.get("sent") == 2

    # Both members advanced to step 1, still active.
    members = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalars().all()
    assert all(m.current_step == 1 and m.state == CampaignLeadState.active for m in members)

    # Second tick (delay_days=0 so due immediately): step 1 sends, then completes.
    out2 = engine.tick(db, now=now + timedelta(seconds=1))
    assert out2.get("sent") == 2

    db.expire_all()
    members = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalars().all()
    assert all(m.state == CampaignLeadState.completed for m in members)

    # Campaign auto-completed; 4 messages recorded (2 leads x 2 steps).
    camp = db.get(Campaign, cid)
    assert camp.state == CampaignState.completed
    msgs = client.get(f"/api/v1/campaigns/{cid}/messages", headers=h).json()
    assert len(msgs) == 4
    assert all(m["status"] == "simulated" for m in msgs)


@requires_db
def test_suppression_skips_member(client, db):
    token, ws = signup(client, email="supp@example.com")
    h = auth_headers(token, ws)
    (lid,) = _make_leads(client, h, ["blocked@x.com"])
    client.post("/api/v1/suppression", headers=h, json={"channel": "email", "value": "blocked@x.com"})
    cid = client.post("/api/v1/campaigns", headers=h, json=_campaign_body()).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": [lid]})
    client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)

    engine.tick(db, now=datetime.now(timezone.utc))
    member = db.execute(select(CampaignLead).where(CampaignLead.campaign_id == cid)).scalar_one()
    assert member.state == CampaignLeadState.skipped
    assert member.last_reason == "not_suppressed"


@requires_db
def test_channel_disabled_blocks_via_can_send(client):
    token, ws = signup(client, email="disabled@example.com")
    h = auth_headers(token, ws)
    (lid,) = _make_leads(client, h, ["c@x.com"])
    # Channel disabled on the campaign — can_send must deny even though a step uses it.
    body = _campaign_body(enabled=False)
    cid = client.post("/api/v1/campaigns", headers=h, json=body).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": [lid]})
    # Launch is rejected because no enabled channel backs the sequence.
    r = client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)
    assert r.status_code == 400

    # preview-send also reports channel_enabled = False.
    pv = client.post(f"/api/v1/campaigns/{cid}/preview-send", headers=h,
                     json={"lead_id": lid, "channel": "email"}).json()
    assert pv["allowed"] is False
    assert pv["checks"]["channel_enabled"] is False


@requires_db
def test_state_machine_invalid_transition(client):
    token, ws = signup(client, email="sm@example.com")
    h = auth_headers(token, ws)
    (lid,) = _make_leads(client, h, ["d@x.com"])
    cid = client.post("/api/v1/campaigns", headers=h, json=_campaign_body()).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": [lid]})
    # Cannot resume a draft (only paused → active).
    assert client.post(f"/api/v1/campaigns/{cid}/resume", headers=h).status_code == 409
    # Launch → pause → resume works.
    client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)
    assert client.post(f"/api/v1/campaigns/{cid}/pause", headers=h).json()["state"] == "paused"
    assert client.post(f"/api/v1/campaigns/{cid}/resume", headers=h).json()["state"] == "active"


@requires_db
def test_paused_campaign_not_processed(client, db):
    token, ws = signup(client, email="paused@example.com")
    h = auth_headers(token, ws)
    (lid,) = _make_leads(client, h, ["e@x.com"])
    cid = client.post("/api/v1/campaigns", headers=h, json=_campaign_body(delay=0)).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": [lid]})
    client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)
    client.post(f"/api/v1/campaigns/{cid}/pause", headers=h)

    out = engine.tick(db, now=datetime.now(timezone.utc))
    assert out == {}  # nothing processed while paused
    msgs = client.get(f"/api/v1/campaigns/{cid}/messages", headers=h).json()
    assert len(msgs) == 0


@requires_db
def test_leads_added_to_active_campaign_are_scheduled(client, db):
    """Leads added AFTER launch must be scheduled and sent, not left pending forever."""
    token, ws = signup(client, email="addactive@example.com")
    h = auth_headers(token, ws)
    (orig,) = _make_leads(client, h, ["orig@x.com"])
    body = _campaign_body()
    body["steps"][1]["delay_days"] = 5  # keep the campaign active after step 0
    cid = client.post("/api/v1/campaigns", headers=h, json=body).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": [orig]})
    client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)

    now = datetime.now(timezone.utc)
    engine.tick(db, now=now)  # orig sends step 0, now waiting 5d on step 1 → campaign stays active

    # Add a new lead while the campaign is already running.
    (late,) = _make_leads(client, h, ["late@x.com"])
    assert client.post(f"/api/v1/campaigns/{cid}/leads", headers=h,
                       json={"lead_ids": [late]}).json()["added"] == 1

    db.expire_all()
    late_member = db.execute(
        select(CampaignLead).where(CampaignLead.campaign_id == cid, CampaignLead.lead_id == late)
    ).scalar_one()
    assert late_member.state == CampaignLeadState.active  # not left pending
    assert late_member.next_action_at is not None

    out = engine.tick(db, now=now + timedelta(seconds=1))
    assert out.get("sent") == 1  # the late-added lead sends


@requires_db
def test_leads_added_while_paused_send_on_resume(client, db):
    """Leads added while paused are activated on resume (not stuck pending)."""
    token, ws = signup(client, email="addpaused@example.com")
    h = auth_headers(token, ws)
    (orig,) = _make_leads(client, h, ["p-orig@x.com"])
    body = _campaign_body(delay=0)
    body["steps"] = [{"channel": "email", "delay_days": 0, "subject": "Hi", "body_template": "Hi"}]
    cid = client.post("/api/v1/campaigns", headers=h, json=body).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": [orig]})
    client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)
    client.post(f"/api/v1/campaigns/{cid}/pause", headers=h)

    (late,) = _make_leads(client, h, ["p-late@x.com"])
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": [late]})
    client.post(f"/api/v1/campaigns/{cid}/resume", headers=h)

    db.expire_all()
    late_member = db.execute(
        select(CampaignLead).where(CampaignLead.campaign_id == cid, CampaignLead.lead_id == late)
    ).scalar_one()
    assert late_member.state == CampaignLeadState.active
    assert late_member.next_action_at is not None


@requires_db
def test_frequency_cap_is_configurable(client, db, monkeypatch):
    """The cross-campaign 24h frequency cap is honored by default but can be disabled
    by setting FREQUENCY_CAP_HOURS=0 (so re-testing the same address isn't blocked)."""
    token, ws = signup(client, email="freqcap@example.com")
    h = auth_headers(token, ws)
    (lid,) = _make_leads(client, h, ["freq@x.com"])
    single = [{"channel": "email", "delay_days": 0, "subject": "Hi", "body_template": "Hi"}]

    # Campaign A contacts the lead.
    bodyA = _campaign_body(name="A"); bodyA["steps"] = single
    cidA = client.post("/api/v1/campaigns", headers=h, json=bodyA).json()["id"]
    client.post(f"/api/v1/campaigns/{cidA}/leads", headers=h, json={"lead_ids": [lid]})
    client.post(f"/api/v1/campaigns/{cidA}/launch", headers=h)
    engine.tick(db, now=datetime.now(timezone.utc))  # A sends to the lead (simulated)

    # Campaign B (different campaign, same lead) — evaluate the gate directly.
    bodyB = _campaign_body(name="B"); bodyB["steps"] = single
    cidB = client.post("/api/v1/campaigns", headers=h, json=bodyB).json()["id"]
    db.expire_all()
    campB = db.get(Campaign, cidB)

    # Default 24h cap → blocked by frequency.
    monkeypatch.setattr("app.services.can_send.settings.FREQUENCY_CAP_HOURS", 24)
    d1 = can_send(db, campaign=campB, channel="email", lead_value="freq@x.com", lead_id=lid)
    assert d1.checks["frequency_ok"] is False

    # Cap disabled → allowed again.
    monkeypatch.setattr("app.services.can_send.settings.FREQUENCY_CAP_HOURS", 0)
    d2 = can_send(db, campaign=campB, channel="email", lead_value="freq@x.com", lead_id=lid)
    assert d2.checks["frequency_ok"] is True


@requires_db
def test_daily_rate_limit(client, db):
    token, ws = signup(client, email="rate@example.com")
    h = auth_headers(token, ws)
    lead_ids = _make_leads(client, h, ["r1@x.com", "r2@x.com", "r3@x.com"])
    # daily_limit=2 on email; single-step campaign.
    body = _campaign_body(daily_limit=2)
    body["steps"] = [{"channel": "email", "delay_days": 0, "subject": "Hi", "body_template": "Hi"}]
    cid = client.post("/api/v1/campaigns", headers=h, json=body).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/leads", headers=h, json={"lead_ids": lead_ids})
    client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)

    out = engine.tick(db, now=datetime.now(timezone.utc))
    assert out.get("sent") == 2                       # third deferred by rate limit
    assert out.get("deferred_rate_limit_ok") == 1
