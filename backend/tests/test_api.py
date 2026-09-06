"""DB-backed API tests: auth, workspace isolation, filtering, suppression, import."""
from __future__ import annotations

from tests.conftest import auth_headers, requires_db, signup


@requires_db
def test_signup_login_me(client):
    token, ws = signup(client, email="a@example.com")
    me = client.get("/api/v1/auth/me", headers=auth_headers(token, ws))
    assert me.status_code == 200
    assert me.json()["email"] == "a@example.com"


@requires_db
def test_duplicate_signup_rejected(client):
    signup(client, email="dup@example.com")
    resp = client.post("/api/v1/auth/signup", json={
        "email": "dup@example.com", "password": "supersecret123", "workspace_name": "X",
    })
    assert resp.status_code == 409


@requires_db
def test_unauthenticated_rejected(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/leads/search", json={}).status_code == 401


@requires_db
def test_lead_crud_and_filtering(client):
    token, ws = signup(client, email="crud@example.com")
    h = auth_headers(token, ws)

    for i in range(3):
        r = client.post("/api/v1/leads", headers=h, json={
            "full_name": f"Person {i}", "email": f"p{i}@x.com", "title": "Engineer",
        })
        assert r.status_code == 201
    client.post("/api/v1/leads", headers=h, json={
        "full_name": "Boss", "email": "boss@x.com", "title": "CEO",
    })

    # Filter by title contains 'Engineer'
    r = client.post("/api/v1/leads/search", headers=h, json={
        "conditions": [{"field": "title", "op": "contains", "value": "Engineer"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert all(item["title"] == "Engineer" for item in body["items"])

    # Full-text-ish search on name
    r = client.post("/api/v1/leads/search", headers=h, json={"search": "Boss"})
    assert r.json()["total"] == 1


@requires_db
def test_workspace_isolation(client):
    # Two separate owners / workspaces.
    t1, ws1 = signup(client, email="ws1@example.com", ws="One")
    t2, ws2 = signup(client, email="ws2@example.com", ws="Two")

    r = client.post("/api/v1/leads", headers=auth_headers(t1, ws1),
                    json={"full_name": "Secret Lead", "email": "secret@x.com"})
    lead_id = r.json()["id"]

    # Workspace 2 must NOT see workspace 1's lead.
    r = client.post("/api/v1/leads/search", headers=auth_headers(t2, ws2), json={})
    assert r.json()["total"] == 0

    # Direct fetch by id across workspaces => 404.
    r = client.get(f"/api/v1/leads/{lead_id}", headers=auth_headers(t2, ws2))
    assert r.status_code == 404

    # User 2 cannot claim workspace 1 on a workspace-scoped endpoint (not a member).
    r = client.post("/api/v1/leads/search", headers=auth_headers(t2, ws1), json={})
    assert r.status_code == 403


@requires_db
def test_suppression_and_import_dedup(client):
    token, ws = signup(client, email="imp@example.com")
    h = auth_headers(token, ws)

    # Suppress one address.
    r = client.post("/api/v1/suppression", headers=h,
                    json={"channel": "email", "value": "blocked@x.com"})
    assert r.status_code == 201

    mapping = {
        "column_map": {"Email": "email", "Name": "full_name"},
        "rows": [
            {"Email": "new1@x.com", "Name": "New One"},
            {"Email": "new1@x.com", "Name": "Dup One"},      # intra-file duplicate
            {"Email": "blocked@x.com", "Name": "Blocked"},   # suppressed
            {"Email": "new2@x.com", "Name": "New Two"},
        ],
        "source_name": "Test CSV",
    }
    r = client.post("/api/v1/imports/csv", headers=h, json=mapping)
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["created"] == 2
    assert res["duplicates_skipped"] == 1
    assert res["suppressed_skipped"] == 1


@requires_db
def test_duplicates_and_merge(client):
    token, ws = signup(client, email="merge@example.com")
    h = auth_headers(token, ws)

    a = client.post("/api/v1/leads", headers=h,
                    json={"full_name": "Jane", "email": "jane@x.com"}).json()
    b = client.post("/api/v1/leads", headers=h,
                    json={"full_name": "Jane D", "email": "jane@x.com", "phone": "+15551234"}).json()

    groups = client.get("/api/v1/leads/duplicates/all", headers=h).json()
    assert len(groups) == 1
    assert set(groups[0]["lead_ids"]) == {a["id"], b["id"]}

    merged = client.post("/api/v1/leads/merge", headers=h,
                         json={"primary_id": a["id"], "duplicate_ids": [b["id"]]})
    assert merged.status_code == 200
    # Primary had no phone; merge should pull it from the duplicate.
    assert merged.json()["phone"] == "+15551234"
    # Duplicate is gone.
    assert client.get(f"/api/v1/leads/{b['id']}", headers=h).status_code == 404
