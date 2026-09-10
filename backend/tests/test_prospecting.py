"""Discovery and campaign integration, entirely offline with isolated test data."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.campaign import Campaign, CampaignLead
from app.models.enums import CampaignLeadState, Channel, MessageDirection, MessageEventType, MessageStatus, Provenance, WorkspaceRole
from app.models.lead import Lead, LeadSource
from app.models.message import Message, MessageEvent
from app.models.user import WorkspaceMember
from app.schemas.prospecting import ProductProfile
from app.services import engine, prospecting, public_web
from app.services.ai.base import NullAIService
from tests.conftest import auth_headers, requires_db, signup

PROFILE = {"name": "ClinicCloud", "overview": "Appointment scheduling software for dental clinics and their patients.",
           "website": "https://cliniccloud.com", "target_customer": "dental clinics", "locations": ["Mumbai"],
           "max_leads": 5}
PAGE = """<html><title>Bright Dental Clinic</title><p>Dental clinics in Mumbai. Contact hello@brightdental.com</p>
<a href='/contact'>Contact</a><script>hidden@brightdental.com</script>
<script type='application/ld+json'>{"geo":{"latitude":19.076,"longitude":72.8777}}</script></html>"""


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr("app.worker.tasks.discover_prospects.apply_async", lambda **kwargs: None)
    monkeypatch.setattr("app.api.routes.campaigns._enqueue_tick", lambda: None)
    monkeypatch.setattr(prospecting, "get_ai_service", lambda: NullAIService())
    monkeypatch.setattr(prospecting.settings, "BRAVE_SEARCH_API_KEY", "")
    monkeypatch.setattr(public_web.PublicWeb, "fetch", lambda self, url: (url, PAGE))


def test_page_contacts_and_locations():
    page = public_web.Page(PAGE + '<a href="mailto:Sales%40brightdental.com?subject=Hi">Sales</a>', "https://brightdental.com")
    assert page.emails() == ["hello@brightdental.com", "sales@brightdental.com"]
    assert page.coordinates() == [(19.076, 72.8777)]
    assert "hidden" not in page.text
    profile = ProductProfile(**PROFILE)
    assert prospecting.location_evidence([page], profile)["location"] == "Mumbai"
    profile.locations = ["Delhi"]
    assert prospecting.location_evidence([page], profile) is None
    profile.radius_km, profile.latitude, profile.longitude = 10, 19.076, 72.8777
    assert prospecting.location_evidence([page], profile)["distance_km"] == 0
    profile.latitude = 28.6
    assert prospecting.location_evidence([page], profile) is None
    assert prospecting.location_evidence([public_web.Page("Mumbai", "https://brightdental.com")], profile) is None


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://user:secret@example.com", "http://localhost:9000"])
def test_reject_unsafe_url_without_connecting(url):
    with pytest.raises(ValueError):
        public_web.public_target(url)


@pytest.mark.parametrize("ips", [["127.0.0.1"], ["169.254.169.254"], ["::1"], ["8.8.8.8", "10.0.0.1"]])
def test_reject_private_or_mixed_dns(monkeypatch, ips):
    monkeypatch.setattr(public_web.socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", (ip, 443)) for ip in ips])
    with pytest.raises(ValueError):
        public_web.public_target("https://business.com")


def test_redirect_rechecks_destination_and_robots(monkeypatch):
    visited = []
    def request(url):
        visited.append(url)
        if "127.0.0.1" in url:
            raise ValueError("Private address")
        if url.endswith("robots.txt"):
            return 200, {}, "User-agent: *\nAllow: /"
        return 302, {"location": "http://127.0.0.1/secret"}, ""
    monkeypatch.setattr(public_web, "_request", request)
    monkeypatch.setattr(public_web.time, "sleep", lambda seconds: None)
    with pytest.raises(ValueError):
        public_web.PublicWeb().fetch("https://business.com")
    assert "http://127.0.0.1/secret" not in visited


def test_robots_disallow(monkeypatch):
    visited = []
    def request(url):
        visited.append(url)
        return 200, {}, "User-agent: *\nDisallow: /"
    monkeypatch.setattr(public_web, "_request", request)
    with pytest.raises(ValueError, match="disallows"):
        public_web.PublicWeb().fetch("https://business.com/private")
    assert visited == ["https://business.com/robots.txt"]


def test_radius_requires_center():
    with pytest.raises(ValueError, match="requires center"):
        ProductProfile(**PROFILE, radius_km=50)


def _setup_run(client, db):
    token, ws = signup(client)
    h = auth_headers(token, ws)
    assert client.put("/api/v1/prospecting/profile", headers=h, json=PROFILE).status_code == 200
    r = client.post("/api/v1/prospecting/runs", headers=h, json={"mode": "websites", "websites": ["https://brightdental.com"]})
    assert r.status_code == 202, r.text
    return ws, h, r.json()["id"]


@requires_db
def test_discovery_to_campaign_bulk_flow(client, db, offline):
    ws, h, rid = _setup_run(client, db)
    prospecting.execute_run(db, rid)
    result = client.get(f"/api/v1/prospecting/runs/{rid}", headers=h).json()
    assert result["status"] == "completed", result
    assert result["sites_scanned"] == 1
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["email"] == "hello@brightdental.com"
    cid = client.post("/api/v1/campaigns", headers=h, json={"name": "Clinic outreach", "test_mode": True,
        "channels": {"email": {"enabled": True, "daily_limit": 50}},
        "steps": [{"channel": "email", "subject": "Hi {{first_name}}", "body_template": "Hello"}]}).json()["id"]
    selection = {"candidate_ids": [candidate["id"]], "campaign_id": cid}
    first = client.post(f"/api/v1/prospecting/runs/{rid}/import", headers=h, json=selection)
    assert first.status_code == 200, first.text
    assert first.json()["created"] == first.json()["added"] == 1
    again = client.post(f"/api/v1/prospecting/runs/{rid}/import", headers=h, json=selection).json()
    assert again["created"] == again["added"] == 0 and again["duplicates"] == 1
    lead = db.scalar(select(Lead).where(Lead.workspace_id == ws))
    assert lead.email_provenance == Provenance.observed and lead.source_id == rid
    assert client.post(f"/api/v1/campaigns/{cid}/launch", headers=h).status_code == 200
    assert engine.tick(db).get("sent") == 1
    report = client.get(f"/api/v1/analytics/email?campaign_id={cid}", headers=h).json()
    assert report["totals"]["sent"] == 0 and report["totals"]["simulated"] == 1
    mail = client.get(f"/api/v1/inbox?direction=outbound&campaign_id={cid}", headers=h).json()
    assert len(mail) == 1 and mail[0]["campaign_name"] == "Clinic outreach" and mail[0]["events"]


@requires_db
def test_discovery_isolation_and_suppression(client, db, offline):
    ws, h, rid = _setup_run(client, db)
    prospecting.execute_run(db, rid)
    candidate = client.get(f"/api/v1/prospecting/runs/{rid}", headers=h).json()["candidates"][0]
    t2, ws2 = signup(client, "other@example.com", "Other")
    h2 = auth_headers(t2, ws2)
    assert client.get(f"/api/v1/prospecting/runs/{rid}", headers=h2).status_code == 404
    assert client.get("/api/v1/prospecting/runs", headers=h2).json() == []
    assert client.post(f"/api/v1/prospecting/runs/{rid}/import", headers=h2, json={"candidate_ids": [candidate["id"]]}).status_code == 404
    client.post("/api/v1/suppression", headers=h, json={"channel": "email", "value": candidate["email"]})
    r = client.post(f"/api/v1/prospecting/runs/{rid}/import", headers=h, json={"candidate_ids": [candidate["id"]]})
    assert r.json()["suppressed"] == 1 and r.json()["created"] == 0
    assert client.post(f"/api/v1/prospecting/runs/{rid}/import", headers=h, json={"candidate_ids": ["fake"]}).status_code == 400


@requires_db
def test_profile_search_key_permissions_and_queue_error(client, db, offline, monkeypatch):
    ws, h, rid = _setup_run(client, db)
    assert client.post("/api/v1/prospecting/runs", headers=h, json={"mode": "search"}).status_code == 400
    assert client.put("/api/v1/prospecting/search-key", headers=h, json={"api_key": "test-private-key"}).status_code == 204
    profile = client.get("/api/v1/prospecting/profile", headers=h)
    assert profile.json()["search_configured"] and "test-private-key" not in profile.text
    assert "test-private-key" not in db.scalar(select(LeadSource).where(LeadSource.kind == prospecting.PROFILE_KIND)).meta["search_key"]
    assert client.post("/api/v1/prospecting/runs", headers=h, json={"mode": "search"}).status_code == 409
    run = db.get(LeadSource, rid); run.meta = {**run.meta, "status": "completed"}; db.commit()
    def unavailable(**kwargs):
        raise RuntimeError("broker secret detail")
    monkeypatch.setattr("app.worker.tasks.discover_prospects.apply_async", unavailable)
    r = client.post("/api/v1/prospecting/runs", headers=h, json={"mode": "search"})
    assert r.status_code == 503 and "secret" not in r.text
    member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == ws))
    member.role = WorkspaceRole.viewer; db.commit()
    assert client.put("/api/v1/prospecting/profile", headers=h, json=PROFILE).status_code == 403
    assert client.put("/api/v1/prospecting/search-key", headers=h, json={"api_key": "another"}).status_code == 403


@requires_db
def test_email_cohort_metrics_and_campaign_filter(client, db):
    token, ws = signup(client); h = auth_headers(token, ws)
    cid = client.post("/api/v1/campaigns", headers=h, json={"name": "Reporting"}).json()["id"]
    now = datetime.now(timezone.utc)
    messages = []
    for status in [MessageStatus.sent, MessageStatus.failed, MessageStatus.queued, MessageStatus.simulated, MessageStatus.bounced]:
        m = Message(workspace_id=ws, campaign_id=cid, channel=Channel.email,
                    direction=MessageDirection.outbound, status=status, created_at=now)
        db.add(m); messages.append(m)
    # Outside the selected campaign and outside the date cohort must be excluded.
    db.add(Message(workspace_id=ws, channel=Channel.email, direction=MessageDirection.outbound, status=MessageStatus.sent))
    db.add(Message(workspace_id=ws, campaign_id=cid, channel=Channel.email, direction=MessageDirection.outbound,
                   status=MessageStatus.sent, created_at=now - timedelta(days=60)))
    db.flush()
    for kind in [MessageEventType.opened, MessageEventType.clicked, MessageEventType.replied]:
        for _ in range(3):
            db.add(MessageEvent(workspace_id=ws, message_id=messages[0].id, type=kind))
    db.add(MessageEvent(workspace_id=ws, message_id=messages[3].id, type=MessageEventType.sent, provenance=Provenance.estimated))
    db.commit()
    r = client.get(f"/api/v1/analytics/email?days=7&campaign_id={cid}", headers=h)
    assert r.status_code == 200, r.text
    data = r.json(); totals = data["totals"]
    assert all(totals[k] == 1 for k in ["sent", "failed", "queued", "simulated", "bounced", "opened", "clicked", "replied"])
    assert totals["attempted"] == 3 and totals["delivered"] == 0
    assert data["rates"]["opened_rate"] == data["rates"]["replied_rate"] == 1
    assert len(data["points"]) == 7 and sum(p["sent"] for p in data["points"]) == 1
    assert client.get("/api/v1/analytics/overview", headers=h).json()["messages_sent"] == 2
    assert client.get("/api/v1/analytics/outreach", headers=h).json()["total_sent"] == 2
    assert client.get("/api/v1/analytics/campaigns", headers=h).json()["campaigns"][0]["messages_sent"] == 2
    mail = client.get(f"/api/v1/inbox?campaign_id={cid}&direction=outbound&message_status=failed", headers=h).json()
    assert len(mail) == 1 and mail[0]["status"] == "failed"
    page1 = client.get(f"/api/v1/inbox?campaign_id={cid}&direction=outbound&limit=2", headers=h).json()
    page2 = client.get(f"/api/v1/inbox?campaign_id={cid}&direction=outbound&limit=2&offset=2", headers=h).json()
    assert not {m["id"] for m in page1} & {m["id"] for m in page2}
    t2, ws2 = signup(client, "other@example.com", "Other")
    other = auth_headers(t2, ws2)
    assert client.get(f"/api/v1/analytics/email?campaign_id={cid}", headers=other).status_code == 404
    assert client.get(f"/api/v1/inbox?direction=outbound&campaign_id={cid}", headers=other).json() == []


def test_brave_search_contract(monkeypatch):
    requests = []
    def respond(request):
        requests.append(request)
        assert request.url.host == "api.search.brave.com"
        assert request.headers["X-Subscription-Token"] == "fixture-key"
        assert request.url.params["count"] == "20"
        import httpx
        return httpx.Response(200, json={"web": {"results": [{"url": "https://brightdental.com"}]},
                                        "query": {"more_results_available": False}})
    import httpx
    original = httpx.Client
    monkeypatch.setattr(prospecting.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    urls, queries = prospecting.discover_urls(ProductProfile(**PROFILE), "fixture-key")
    assert urls == ["https://brightdental.com"] and "Mumbai" in queries[0]
    assert len(requests) == 1


@requires_db
def test_bulk_waiting_does_not_exhaust_retry_budget(client, db, offline):
    ws, h, rid = _setup_run(client, db); prospecting.execute_run(db, rid)
    candidate = client.get(f"/api/v1/prospecting/runs/{rid}", headers=h).json()["candidates"][0]
    cid = client.post("/api/v1/campaigns", headers=h, json={"name": "Weekday campaign", "test_mode": True,
        "channels": {"email": {"enabled": True, "schedule": {"days": []}}},
        "steps": [{"channel": "email", "body_template": "Hello"}]}).json()["id"]
    client.post(f"/api/v1/prospecting/runs/{rid}/import", headers=h, json={"candidate_ids": [candidate["id"]], "campaign_id": cid})
    client.post(f"/api/v1/campaigns/{cid}/launch", headers=h)
    member = db.scalar(select(CampaignLead).where(CampaignLead.campaign_id == cid))
    for _ in range(engine.MAX_ATTEMPTS + 2):
        assert engine.process_member(db, member).startswith("deferred_schedule")
    assert member.state == CampaignLeadState.active and member.attempts == 0


@requires_db
def test_parallel_tick_skips_locked_campaign(client, db, engine: object, offline):
    from sqlalchemy.orm import Session
    cid = None
    token, ws = signup(client); h = auth_headers(token, ws)
    cid = client.post("/api/v1/campaigns", headers=h, json={"name": "Locked"}).json()["id"]
    campaign = db.get(Campaign, cid)
    from app.models.enums import CampaignState
    campaign.state = CampaignState.active; db.commit()
    db.scalar(select(Campaign).where(Campaign.id == cid).with_for_update())
    from app.services.engine import tick
    with Session(engine) as other:
        assert tick(other) == {}
    db.rollback()
