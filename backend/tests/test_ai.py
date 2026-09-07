"""Phase 4 — Gemma AI. Pure parsing/guardrail tests run without a network or DB;
endpoint + persistence tests stub the AIService so no real model is called."""
from __future__ import annotations

from typing import Any

import pytest

from app.services.ai.base import AIResult, AIService, NullAIService
from app.services.ai.deepseek import DeepSeekAIService
from app.services.ai.gemma import GemmaAIService
from tests.conftest import auth_headers, requires_db, signup


# ---------------------------------------------------------------------------
# Pure: JSON parsing + guardrails (no network)
# ---------------------------------------------------------------------------

def test_parse_json_plain():
    assert GemmaAIService._parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_strips_code_fences():
    assert GemmaAIService._parse_json('```json\n{"a": 2}\n```') == {"a": 2}


def test_parse_json_extracts_embedded_object():
    assert GemmaAIService._parse_json('Sure! {"a": 3} hope that helps') == {"a": 3}


def test_parse_json_returns_none_on_garbage():
    assert GemmaAIService._parse_json("not json at all") is None
    assert GemmaAIService._parse_json("") is None
    assert GemmaAIService._parse_json("[1,2,3]") is None  # not an object


def test_parse_json_strips_think_block():
    # A reasoning trace that leaks despite thinking=False must not derail parsing.
    raw = '<think>the ICP mentions {"x": 1}, so I should weigh that</think>\n{"score": 80}'
    assert GemmaAIService._parse_json(raw, prefer_keys=("score",)) == {"score": 80}


class _StubGemma(GemmaAIService):
    """GemmaAIService with the network call stubbed to a canned response."""

    def __init__(self, text: str, *, raise_exc: Exception | None = None):
        super().__init__(api_key="test-key", model_id="gemma-3-27b-it")
        self._text = text
        self._raise = raise_exc

    def _call(self, prompt, *, temperature=0.4, max_tokens=1024):
        if self._raise:
            raise self._raise
        return self._text, 42


def test_run_unknown_on_unparseable_output():
    svc = _StubGemma("the model rambled without json")
    res = svc.qualify_lead({"full_name": "Ada"}, {})
    assert res.status == "unknown"
    assert res.output == {}


def test_run_error_on_transport_failure():
    svc = _StubGemma("", raise_exc=RuntimeError("connection reset"))
    res = svc.classify_reply("hello")
    assert res.status == "error"
    assert "connection reset" in (res.error or "")


def test_qualify_clamps_score_and_validates_verdict():
    svc = _StubGemma('{"score": 250, "verdict": "amazing", "rationale": "x", "assumptions": ["a1"]}')
    res = svc.qualify_lead({"full_name": "Ada", "title": "CTO"}, {"industry": "SaaS"})
    assert res.status == "ok"
    assert res.output["score"] == 100          # clamped into 0..100
    assert res.output["verdict"] == "unknown"  # invalid verdict normalized
    assert res.assumptions == ["a1"]           # pulled out of output


def test_qualify_handles_null_score():
    svc = _StubGemma('{"score": null, "verdict": "unknown", "rationale": null}')
    res = svc.qualify_lead({"full_name": "Ada"}, {})
    assert res.status == "ok"
    assert res.output["score"] is None


def test_classify_reply_normalizes_unknown_intent():
    svc = _StubGemma('{"intent": "definitely_maybe", "sentiment": "positive", "confidence": 0.9}')
    res = svc.classify_reply("Sounds good, let's talk")
    assert res.output["intent"] == "unknown"


class _StubDeepSeek(DeepSeekAIService):
    """DeepSeekAIService with the network call stubbed to a canned response."""

    def __init__(self, text: str, *, raise_exc: Exception | None = None):
        super().__init__(api_key="test-key", model_id="deepseek-ai/deepseek-v4-pro-0813",
                         base_url="https://example.test/v1")
        self._text = text
        self._raise = raise_exc

    def _call(self, prompt, *, temperature=0.4, max_tokens=4096):
        if self._raise:
            raise self._raise
        return self._text, 99


def test_deepseek_shares_parsing_and_guardrails():
    svc = _StubDeepSeek('{"score": 300, "verdict": "hot", "rationale": "x"}')
    res = svc.qualify_lead({"full_name": "Ada", "title": "CTO"}, {})
    assert res.status == "ok"
    assert res.output["score"] == 100          # clamped by the shared base
    assert res.output["verdict"] == "unknown"  # invalid verdict normalized
    assert res.model == "deepseek-ai/deepseek-v4-pro-0813"


def test_deepseek_degrades_on_transport_failure():
    svc = _StubDeepSeek("", raise_exc=RuntimeError("502 bad gateway"))
    res = svc.classify_reply("hi")
    assert res.status == "error" and "502" in (res.error or "")


def test_deepseek_extracts_json_after_leaked_reasoning():
    svc = _StubDeepSeek('<think>let me weigh {"industry": "x"}</think> {"intent": "interested", '
                        '"sentiment": "positive", "confidence": 0.9}')
    res = svc.classify_reply("Yes please")
    assert res.status == "ok" and res.output["intent"] == "interested"


def test_factory_selects_by_provider(monkeypatch):
    import app.services.ai.factory as f

    monkeypatch.setattr(f.settings, "AI_PROVIDER", "auto", raising=False)
    monkeypatch.setattr(f.settings, "NVIDIA_API_KEY", "nv-key", raising=False)
    monkeypatch.setattr(f.settings, "GEMINI_API_KEY", "gm-key", raising=False)
    f.get_ai_service.cache_clear()
    assert isinstance(f.get_ai_service(), DeepSeekAIService)  # DeepSeek wins in auto

    monkeypatch.setattr(f.settings, "AI_PROVIDER", "gemma", raising=False)
    f.get_ai_service.cache_clear()
    assert isinstance(f.get_ai_service(), GemmaAIService)

    monkeypatch.setattr(f.settings, "AI_PROVIDER", "deepseek", raising=False)
    monkeypatch.setattr(f.settings, "NVIDIA_API_KEY", "", raising=False)
    f.get_ai_service.cache_clear()
    assert isinstance(f.get_ai_service(), NullAIService)  # forced provider, key missing
    f.get_ai_service.cache_clear()


def test_null_service_never_fabricates():
    svc = NullAIService()
    assert not svc.enabled
    for res in (
        svc.qualify_lead({}, {}),
        svc.generate_email({}, {}),
        svc.classify_reply("hi"),
        svc.nl_to_filters("x"),
        svc.copilot("y"),
    ):
        assert res.status == "unknown"


# ---------------------------------------------------------------------------
# Fake service for endpoint tests
# ---------------------------------------------------------------------------

class FakeAIService(AIService):
    model_id = "fake-model"

    @property
    def enabled(self) -> bool:
        return True

    def qualify_lead(self, lead, icp=None):
        return AIResult(status="ok", kind="qualify_lead", model=self.model_id,
                        output={"score": 87, "verdict": "strong", "rationale": "Great fit",
                                "signals": ["CTO", "SaaS"]}, assumptions=["assumed timezone"])

    def generate_email(self, lead, context=None):
        return AIResult(status="ok", kind="generate_email", model=self.model_id,
                        output={"subject": "Quick question", "body": "Hi there, ..."})

    def generate_linkedin_message(self, lead, context=None):
        return AIResult(status="ok", kind="generate_linkedin_message", model=self.model_id,
                        output={"body": "Loved your work"})

    def generate_follow_up(self, thread, context=None):
        return AIResult(status="ok", kind="generate_follow_up", model=self.model_id,
                        output={"subject": None, "body": "Just following up"})

    def classify_reply(self, message, context=None):
        return AIResult(status="ok", kind="classify_reply", model=self.model_id,
                        output={"intent": "interested", "sentiment": "positive", "confidence": 0.95})

    def summarize_conversation(self, thread):
        return AIResult(status="ok", kind="summarize_conversation", model=self.model_id, output={})

    def recommend_next_action(self, lead, context=None):
        return AIResult(status="ok", kind="recommend_next_action", model=self.model_id, output={})

    def analyze_campaign(self, stats):
        return AIResult(status="ok", kind="analyze_campaign", model=self.model_id,
                        output={"summary": "Solid", "strengths": ["reply rate"],
                                "issues": [], "recommendations": ["add a step"]})

    def nl_to_filters(self, query, schema=None):
        return AIResult(status="ok", kind="nl_to_filters", model=self.model_id,
                        output={"match": "all",
                                "conditions": [
                                    {"field": "title", "op": "contains", "value": "CTO"},
                                    {"field": "not_a_real_field", "op": "eq", "value": "x"},  # dropped
                                ],
                                "sort_by": "score", "sort_dir": "desc"})

    def copilot(self, question, context=None):
        return AIResult(status="ok", kind="copilot", model=self.model_id,
                        output={"answer": f"You have {context.get('total_leads')} leads.",
                                "used_context": True})


@pytest.fixture
def use_fake_ai(monkeypatch):
    fake = FakeAIService()
    monkeypatch.setattr("app.api.routes.ai.get_ai_service", lambda: fake)
    return fake


def _make_lead(client, headers, **fields):
    body = {"full_name": "Ada Lovelace", "title": "CTO", "email": "ada@example.com", **fields}
    r = client.post("/api/v1/leads", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@requires_db
def test_ai_status_disabled_with_null_service(client, monkeypatch):
    # Force the null service so the test is deterministic whether or not a real
    # GEMINI_API_KEY is present in the environment.
    monkeypatch.setattr("app.api.routes.ai.get_ai_service", lambda: NullAIService())
    token, ws = signup(client)
    h = auth_headers(token, ws)
    r = client.get("/api/v1/ai/status", headers=h)
    assert r.status_code == 200
    assert r.json()["enabled"] is False


@requires_db
def test_ai_status_enabled_with_fake(client, use_fake_ai):
    token, ws = signup(client)
    h = auth_headers(token, ws)
    r = client.get("/api/v1/ai/status", headers=h)
    assert r.json() == {"enabled": True, "model": "fake-model"}


@requires_db
def test_qualify_persists_score_and_audit(client, use_fake_ai):
    token, ws = signup(client)
    h = auth_headers(token, ws)
    lead_id = _make_lead(client, h)

    r = client.post(f"/api/v1/ai/qualify/{lead_id}", json={}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["output"]["score"] == 87
    assert body["assumptions"] == ["assumed timezone"]

    # Persisted on the lead.
    lead = client.get(f"/api/v1/leads/{lead_id}", headers=h).json()
    assert lead["score"] == 87
    assert lead["ai_qualification"]["verdict"] == "strong"
    assert lead["status"] == "qualified"  # verdict strong bumped it from "new"

    # Audit trail row exists.
    gens = client.get("/api/v1/ai/generations", headers=h).json()
    assert any(g["kind"] == "qualify_lead" and g["status"] == "ok" for g in gens)


@requires_db
def test_qualify_bulk(client, use_fake_ai):
    token, ws = signup(client)
    h = auth_headers(token, ws)
    ids = [_make_lead(client, h, email=f"l{i}@example.com") for i in range(3)]
    r = client.post("/api/v1/ai/qualify", json={"lead_ids": ids}, headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["processed"] == 3
    assert all(item["score"] == 87 for item in data["results"])


@requires_db
def test_nl_search_builds_filter_and_drops_bad_conditions(client, use_fake_ai):
    token, ws = signup(client)
    h = auth_headers(token, ws)
    _make_lead(client, h)  # a CTO

    r = client.post("/api/v1/ai/nl-search", json={"query": "CTOs sorted by score"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    # The invalid field condition is dropped; only the valid one survives.
    fields = [c["field"] for c in body["filter"]["conditions"]]
    assert fields == ["title"]
    assert body["filter"]["sort_by"] == "score"
    assert body["leads"]["total"] >= 1


@requires_db
def test_classify_reply_endpoint(client, use_fake_ai):
    token, ws = signup(client)
    h = auth_headers(token, ws)
    r = client.post("/api/v1/ai/classify-reply", json={"message": "Yes, interested!"}, headers=h)
    assert r.status_code == 200
    assert r.json()["output"]["intent"] == "interested"


@requires_db
def test_classify_reply_requires_input(client, use_fake_ai):
    token, ws = signup(client)
    h = auth_headers(token, ws)
    r = client.post("/api/v1/ai/classify-reply", json={}, headers=h)
    assert r.status_code == 422


@requires_db
def test_copilot_uses_workspace_context(client, use_fake_ai):
    token, ws = signup(client)
    h = auth_headers(token, ws)
    _make_lead(client, h)
    r = client.post("/api/v1/ai/copilot", json={"question": "How many leads?"}, headers=h)
    assert r.status_code == 200
    assert "1 leads" in r.json()["output"]["answer"]


@requires_db
def test_generate_email_endpoint(client, use_fake_ai):
    token, ws = signup(client)
    h = auth_headers(token, ws)
    lead_id = _make_lead(client, h)
    r = client.post("/api/v1/ai/generate/email", json={"lead_id": lead_id}, headers=h)
    assert r.status_code == 200
    assert r.json()["output"]["subject"] == "Quick question"


@requires_db
def test_qualify_workspace_isolation(client, use_fake_ai):
    t1, ws1 = signup(client, email="a@example.com", ws="Acme")
    t2, ws2 = signup(client, email="b@example.com", ws="Beta")
    lead_id = _make_lead(client, auth_headers(t1, ws1))
    # Workspace 2 cannot qualify workspace 1's lead.
    r = client.post(f"/api/v1/ai/qualify/{lead_id}", json={}, headers=auth_headers(t2, ws2))
    assert r.status_code == 404


@requires_db
def test_disabled_ai_returns_unknown_not_error(client, monkeypatch):
    """With AI disabled the endpoints still succeed, returning status 'unknown'."""
    monkeypatch.setattr("app.api.routes.ai.get_ai_service", lambda: NullAIService())
    token, ws = signup(client)
    h = auth_headers(token, ws)
    lead_id = _make_lead(client, h)
    r = client.post(f"/api/v1/ai/qualify/{lead_id}", json={}, headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "unknown"
