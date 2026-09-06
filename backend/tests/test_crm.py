"""Phase 7 — CRM: tasks/meetings, notes, unified lead timeline, and the pipeline
board. DB-backed against the test database."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.enums import Channel, MessageDirection, MessageStatus
from app.models.message import Message
from tests.conftest import auth_headers, requires_db, signup


def _lead(client, h, name="Ada Byron", email="ada@x.com"):
    r = client.post("/api/v1/leads", headers=h, json={"full_name": name, "email": email})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _set_status(client, h, lead_id, st):
    assert client.patch(f"/api/v1/leads/{lead_id}", headers=h, json={"status": st}).status_code == 200


@requires_db
def test_task_lifecycle(client):
    token, ws = signup(client, email="crm-task@example.com")
    h = auth_headers(token, ws)
    lid = _lead(client, h)
    due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = client.post("/api/v1/crm/tasks", headers=h,
                    json={"title": "Call Ada", "type": "call", "lead_id": lid, "due_at": due})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["status"] == "open" and t["lead_name"] == "Ada Byron" and t["assignee_name"]

    # Default assignee is the creator, listed under "open".
    assert len(client.get("/api/v1/crm/tasks?scope=open", headers=h).json()) == 1

    # Patch → complete → gone from open, present in done.
    client.patch(f"/api/v1/crm/tasks/{t['id']}", headers=h, json={"title": "Call Ada Lovelace"})
    r = client.post(f"/api/v1/crm/tasks/{t['id']}/complete", headers=h)
    assert r.json()["status"] == "done" and r.json()["completed_at"]
    assert client.get("/api/v1/crm/tasks?scope=open", headers=h).json() == []
    done = client.get("/api/v1/crm/tasks?scope=done", headers=h).json()
    assert done[0]["title"] == "Call Ada Lovelace"

    client.delete(f"/api/v1/crm/tasks/{t['id']}", headers=h)
    assert client.get("/api/v1/crm/tasks?scope=all", headers=h).json() == []


@requires_db
def test_task_scopes_overdue_upcoming(client):
    token, ws = signup(client, email="crm-scope@example.com")
    h = auth_headers(token, ws)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    client.post("/api/v1/crm/tasks", headers=h, json={"title": "late", "due_at": past})
    client.post("/api/v1/crm/tasks", headers=h, json={"title": "soon", "due_at": future})
    overdue = client.get("/api/v1/crm/tasks?scope=overdue", headers=h).json()
    upcoming = client.get("/api/v1/crm/tasks?scope=upcoming", headers=h).json()
    assert [t["title"] for t in overdue] == ["late"]
    assert [t["title"] for t in upcoming] == ["soon"]


@requires_db
def test_notes_crud(client):
    token, ws = signup(client, email="crm-note@example.com")
    h = auth_headers(token, ws)
    lid = _lead(client, h)
    r = client.post(f"/api/v1/crm/leads/{lid}/notes", headers=h, json={"body": "Met at conference."})
    assert r.status_code == 201, r.text
    note = r.json()
    assert note["author_name"] and note["body"] == "Met at conference."
    listed = client.get(f"/api/v1/crm/leads/{lid}/notes", headers=h).json()
    assert len(listed) == 1
    client.delete(f"/api/v1/crm/notes/{note['id']}", headers=h)
    assert client.get(f"/api/v1/crm/leads/{lid}/notes", headers=h).json() == []


@requires_db
def test_timeline_merges_sources(client, db):
    token, ws = signup(client, email="crm-timeline@example.com")
    h = auth_headers(token, ws)
    lid = _lead(client, h)
    client.post(f"/api/v1/crm/leads/{lid}/notes", headers=h, json={"body": "A note"})
    client.post("/api/v1/crm/tasks", headers=h, json={"title": "A task", "lead_id": lid})
    db.add(Message(
        workspace_id=ws, lead_id=lid, channel=Channel.email, direction=MessageDirection.outbound,
        status=MessageStatus.sent, subject="Intro", body="Hello Ada", to_address="ada@x.com",
    ))
    db.commit()

    tl = client.get(f"/api/v1/crm/leads/{lid}/timeline", headers=h).json()
    kinds = {i["kind"] for i in tl}
    assert kinds == {"message", "note", "task"}
    msg = next(i for i in tl if i["kind"] == "message")
    assert msg["channel"] == "email" and msg["title"] == "Intro"


@requires_db
def test_pipeline_groups_by_stage(client):
    token, ws = signup(client, email="crm-pipe@example.com")
    h = auth_headers(token, ws)
    a, b, c = _lead(client, h, "A", "a@x.com"), _lead(client, h, "B", "b@x.com"), _lead(client, h, "C", "c@x.com")
    _set_status(client, h, b, "qualified")
    _set_status(client, h, c, "won")
    # An open task on lead A → badge count.
    client.post("/api/v1/crm/tasks", headers=h, json={"title": "todo", "lead_id": a})

    data = client.get("/api/v1/crm/pipeline", headers=h).json()
    stages = {s["status"]: s for s in data["stages"]}
    assert stages["new"]["count"] == 1 and stages["qualified"]["count"] == 1 and stages["won"]["count"] == 1
    new_card = stages["new"]["cards"][0]
    assert new_card["full_name"] == "A" and new_card["open_tasks"] == 1
    assert len(stages["new"]["cards"]) == 1


@requires_db
def test_workspace_isolation(client):
    t1, ws1 = signup(client, email="crm-iso1@example.com")
    t2, ws2 = signup(client, email="crm-iso2@example.com", ws="Other")
    h1, h2 = auth_headers(t1, ws1), auth_headers(t2, ws2)
    lid = _lead(client, h1)
    tid = client.post("/api/v1/crm/tasks", headers=h1, json={"title": "mine", "lead_id": lid}).json()["id"]
    # ws2 can't see or touch ws1's task or lead notes.
    assert client.get("/api/v1/crm/tasks?scope=all", headers=h2).json() == []
    assert client.patch(f"/api/v1/crm/tasks/{tid}", headers=h2, json={"title": "hijack"}).status_code == 404
    assert client.get(f"/api/v1/crm/leads/{lid}/notes", headers=h2).status_code == 404
