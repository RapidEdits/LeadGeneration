"""Live Gemma 3 27B implementation via Google's Generative Language API.

One HTTP call per task (`_call`), isolated so tests can stub it without a network.
Output is parsed defensively (fences stripped, first JSON object extracted); any
network, HTTP, or parse failure degrades to `status="unknown"` with safe empty
output — the guardrail is "unknown over fabrication", enforced here, not upstream.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.services.ai import prompts
from app.services.ai.base import AIResult, AIService

logger = logging.getLogger(__name__)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class GemmaAIService(AIService):
    def __init__(self, api_key: str, model_id: str, timeout: float = 45.0) -> None:
        self._api_key = api_key
        self.model_id = model_id
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    # ---- transport (stub this in tests) ----

    def _call(self, prompt: str, *, temperature: float = 0.4, max_tokens: int = 2048) -> tuple[str, int | None]:
        """Return (text, token_count). Raises on transport/HTTP error."""
        url = _ENDPOINT.format(model=self.model_id)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        resp = httpx.post(
            url, params={"key": self._api_key}, json=payload, timeout=self._timeout
        )
        # Some Gemma models on the API reject responseMimeType — retry once without it.
        if resp.status_code == 400 and "responseMimeType" in resp.text:
            payload["generationConfig"].pop("responseMimeType", None)
            resp = httpx.post(
                url, params={"key": self._api_key}, json=payload, timeout=self._timeout
            )
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("No candidates in response")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        tokens = (data.get("usageMetadata") or {}).get("totalTokenCount")
        return text, tokens

    # ---- parsing ----

    @staticmethod
    def _iter_json_objects(text: str):
        """Yield every top-level balanced {...} substring, string-aware so braces
        inside quoted values don't confuse the matching."""
        depth = 0
        start = -1
        in_str = False
        escape = False
        for i, ch in enumerate(text):
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start >= 0:
                        yield text[start : i + 1]

    @classmethod
    def _parse_json(cls, text: str, prefer_keys: tuple[str, ...] = ()) -> dict[str, Any] | None:
        """Extract a JSON object even from a verbose/reasoning model.

        Reasoning models (e.g. Gemma 4) wrap the answer in a scratchpad that itself
        contains brace-quoted fragments (echoed context, the schema spec), so a plain
        json.loads fails and the outermost span is junk. We scan for every balanced
        object and score candidates: ones carrying the task's expected keys win over the
        context echo; later and richer objects break ties (the real answer comes last).
        """
        if not text:
            return None
        cleaned = _FENCE_RE.sub("", text.strip())
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        best: dict[str, Any] | None = None
        best_score: tuple[int, int, int] = (-1, -1, -1)
        for pos, candidate in enumerate(cls._iter_json_objects(cleaned)):
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or not obj:
                continue
            matched = sum(1 for k in prefer_keys if k in obj)
            score = (matched, len(obj), pos)
            if score >= best_score:
                best_score, best = score, obj
        return best

    def _run(self, kind: str, prompt: str, facts: dict, *, temperature: float = 0.4,
             prefer_keys: tuple[str, ...] = ()) -> AIResult:
        started = time.monotonic()
        try:
            text, tokens = self._call(prompt, temperature=temperature)
        except Exception as exc:  # noqa: BLE001 — any failure degrades to "unknown", never raises upstream
            logger.warning("Gemma call failed (%s): %s", kind, exc)
            return AIResult(status="error", kind=kind, model=self.model_id, error=str(exc))
        latency = int((time.monotonic() - started) * 1000)
        parsed = self._parse_json(text, prefer_keys)
        if parsed is None:
            logger.warning("Gemma returned unparseable output for %s", kind)
            return AIResult(status="unknown", kind=kind, model=self.model_id,
                            latency_ms=latency, tokens=tokens, error="Unparseable model output")
        assumptions = parsed.pop("assumptions", None) or []
        if not isinstance(assumptions, list):
            assumptions = [str(assumptions)]
        return AIResult(status="ok", kind=kind, model=self.model_id, output=parsed,
                        assumptions=[str(a) for a in assumptions], latency_ms=latency, tokens=tokens)

    # ---- public API ----

    def qualify_lead(self, lead, icp=None):
        prompt, facts = prompts.qualify_lead(lead, icp)
        res = self._run("qualify_lead", prompt, facts, temperature=0.2,
                        prefer_keys=("score", "verdict", "rationale"))
        if res.ok:
            out = res.output
            score = out.get("score")
            try:
                out["score"] = None if score is None else max(0, min(100, int(round(float(score)))))
            except (TypeError, ValueError):
                out["score"] = None
            if out.get("verdict") not in {"strong", "medium", "weak", "unknown"}:
                out["verdict"] = "unknown"
        return res

    def generate_email(self, lead, context=None):
        prompt, facts = prompts.generate_email(lead, context)
        return self._run("generate_email", prompt, facts, temperature=0.6,
                         prefer_keys=("subject", "body"))

    def generate_linkedin_message(self, lead, context=None):
        prompt, facts = prompts.generate_linkedin_message(lead, context)
        return self._run("generate_linkedin_message", prompt, facts, temperature=0.6,
                         prefer_keys=("body",))

    def generate_follow_up(self, thread, context=None):
        prompt, facts = prompts.generate_follow_up(thread, context)
        return self._run("generate_follow_up", prompt, facts, temperature=0.6,
                         prefer_keys=("subject", "body"))

    def classify_reply(self, message, context=None):
        prompt, facts = prompts.classify_reply(message, context)
        res = self._run("classify_reply", prompt, facts, temperature=0.1,
                        prefer_keys=("intent", "sentiment", "confidence"))
        if res.ok:
            valid = {"interested", "not_interested", "question", "meeting_request",
                     "unsubscribe", "out_of_office", "wrong_person", "other", "unknown"}
            if res.output.get("intent") not in valid:
                res.output["intent"] = "unknown"
        return res

    def summarize_conversation(self, thread):
        prompt, facts = prompts.summarize_conversation(thread)
        return self._run("summarize_conversation", prompt, facts, temperature=0.3,
                         prefer_keys=("summary", "next_action"))

    def recommend_next_action(self, lead, context=None):
        prompt, facts = prompts.recommend_next_action(lead, context)
        return self._run("recommend_next_action", prompt, facts, temperature=0.3,
                         prefer_keys=("action", "rationale"))

    def analyze_campaign(self, stats):
        prompt, facts = prompts.analyze_campaign(stats)
        return self._run("analyze_campaign", prompt, facts, temperature=0.3,
                         prefer_keys=("summary", "recommendations", "strengths", "issues"))

    def nl_to_filters(self, query, schema=None):
        prompt, facts = prompts.nl_to_filters(query, schema)
        res = self._run("nl_to_filters", prompt, facts, temperature=0.0,
                        prefer_keys=("conditions", "match", "sort_by"))
        if res.ok and not isinstance(res.output.get("conditions"), list):
            res.output["conditions"] = []
        return res

    def copilot(self, question, context=None):
        prompt, facts = prompts.copilot(question, context)
        return self._run("copilot", prompt, facts, temperature=0.4,
                         prefer_keys=("answer",))
