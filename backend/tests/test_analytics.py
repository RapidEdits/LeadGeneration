"""Phase 8 — Analytics: overview KPIs, funnel, outreach performance, time series,
per-campaign performance, and AI insights degradation. DB-backed."""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.enums import (
    Channel,
    MessageDirection,
    MessageEventType,
    MessageStatus,
)
from app.models.message import Message, MessageEvent
from app.services.ai.base import NullAIService
from tests.conftest import auth_headers, requires_db, signup


def _lead(client, h, name, email, status="new"):
    lid = client.post("/api/v1/leads", headers=h, json={"full_name": name, "email": email}).json()["id"]
    if status != "new":
        client.patch(f"/api/v1/leads/{lid}", headers=h, json={"status": status})
    return lid


@requires_db
def test_overview_counts(client):
    token, ws = signup(client, email="an-ov@example.com")
    h = auth_headers(token, ws)
    _lead(client, h, "A", "a@x.com", "qualified")
    _lead(client, h, "B", "b@x.com", "won")
    _lead(client, h, "C", "c@x.com", "lost")

    o = client.get("/api/v1/analytics/overview", headers=h).json()
    assert o["total_leads"] == 3
    assert o["new_leads"] == 3          # all created inside the default 30d window
    assert o["qualified_leads"] == 1
    assert o["won_leads"] == 1 and o["lost_leads"] == 1
    assert o["win_rate"] == 0.5


@requires_db
def test_funnel_is_cumulative(client):
    token, ws = signup(client, email="an-fn@example.com")
    h = auth_headers(token, ws)
    _lead(client, h, "A", "a@x.com", "new")
    _lead(client, h, "B", "b@x.com", "contacted")
    _lead(client, h, "C", "c@x.com", "won")

    stages = {s["status"]: s for s in client.get("/api/v1/analytics/funnel", headers=h).json()["stages"]}
    assert stages["new"]["count"] == 3          # everyone
    assert stages["contacted"]["count"] == 2    # contacted + won
    assert stages["won"]["count"] == 1
    assert stages["contacted"]["conversion_from_top"] == round(2 / 3, 4)


@requires_db
def test_outreach_and_timeseries(client, db):
    token, ws = signup(client, email="an-out@example.com")
    h = auth_headers(token, ws)
    lid = _lead(client, h, "A", "a@x.com")

    m = Message(workspace_id=ws, lead_id=lid, channel=Channel.email,
                direction=MessageDirection.outbound, status=MessageStatus.sent,
                subject="Hi", body="Hello", to_address="a@x.com")
    db.add(m)
    db.flush()
    db.add(MessageEvent(workspace_id=ws, message_id=m.id, type=MessageEventType.opened))
    db.add(Message(workspace_id=ws, lead_id=lid, channel=Channel.email,
                   direction=MessageDirection.inbound, status=MessageStatus.replied,
                   body="Sure"))
    db.commit()

    out = client.get("/api/v1/analytics/outreach", headers=h).json()
    assert out["total_sent"] == 1 and out["total_opened"] == 1 and out["total_replied"] == 1
    assert out["open_rate"] == 1.0 and out["reply_rate"] == 1.0
    email = next(c for c in out["by_channel"] if c["channel"] == "email")
    assert email["sent"] == 1 and email["opened"] == 1 and email["replied"] == 1

    ts = client.get("/api/v1/analytics/timeseries?days=7", headers=h).json()
    assert len(ts["points"]) == 7
    today = ts["points"][-1]
    assert today["messages_sent"] == 1 and today["replies"] == 1 and today["leads_created"] == 1


@requires_db
def test_campaigns_performance_and_insights_degrade(client, monkeypatch):
    # Force the null service so the degradation contract is tested deterministically,
    # regardless of whether a real AI key is present in the environment.
    monkeypatch.setattr("app.api.routes.analytics.get_ai_service", lambda: NullAIService())
    token, ws = signup(client, email="an-cmp@example.com")
    h = auth_headers(token, ws)
    client.post("/api/v1/campaigns", headers=h, json={
        "name": "Q3 Outbound", "test_mode": True, "approval_mode": "auto",
        "channels": {"email": {"enabled": True}}, "steps": [],
    })
    perf = client.get("/api/v1/analytics/campaigns", headers=h).json()["campaigns"]
    assert len(perf) == 1 and perf[0]["name"] == "Q3 Outbound"
    assert perf[0]["messages_sent"] == 0 and perf[0]["reply_rate"] == 0.0

    # Insights never 500s and never fabricates: the null seam returns "unknown".
    ins = client.post("/api/v1/analytics/insights", headers=h)
    assert ins.status_code == 200
    assert ins.json()["result"]["status"] == "unknown"


@requires_db
def test_workspace_isolation(client):
    t1, ws1 = signup(client, email="an-iso1@example.com")
    t2, ws2 = signup(client, email="an-iso2@example.com", ws="Other")
    h1 = auth_headers(t1, ws1)
    _lead(client, h1, "A", "a@x.com", "won")
    o2 = client.get("/api/v1/analytics/overview", headers=auth_headers(t2, ws2)).json()
    assert o2["total_leads"] == 0 and o2["won_leads"] == 0
