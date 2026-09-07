"""Shared base for AI services backed by a chat model that returns JSON.

Holds everything that is model-agnostic: the defensive JSON extraction (fences
stripped, `<think>` blocks removed, every balanced object scanned and scored so
the real answer wins over an echoed-context object), the per-task temperature /
expected-key config, and the output post-processing / guardrails.

A concrete subclass only implements `_call(prompt, *, temperature, max_tokens)
-> (text, tokens)` for its transport, plus `__init__` / `enabled` / `model_id`.
Any transport, HTTP, or parse failure degrades to `status="error"` / `"unknown"`
with safe empty output — "unknown over fabrication", enforced here.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.services.ai import prompts
from app.services.ai.base import AIResult, AIService

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


class JsonModelService(AIService):
    """AIService for any chat model we prompt to return a single JSON object."""

    # ---- transport (implemented by subclasses; stub this in tests) ----

    def _call(self, prompt: str, *, temperature: float = 0.4, max_tokens: int = 4096) -> tuple[str, int | None]:
        raise NotImplementedError

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

        Reasoning models wrap the answer in a scratchpad (or `<think>` block) that
        itself contains brace-quoted fragments (echoed context, the schema spec), so
        a plain json.loads fails and the outermost span is junk. We strip thinking,
        then scan for every balanced object and score candidates: ones carrying the
        task's expected keys win; later, richer objects break ties.
        """
        if not text:
            return None
        cleaned = _THINK_RE.sub("", text).strip()
        cleaned = _FENCE_RE.sub("", cleaned.strip())
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

    # ---- run one task ----

    def _run(self, kind: str, prompt: str, facts: dict, *, temperature: float = 0.4,
             prefer_keys: tuple[str, ...] = ()) -> AIResult:
        started = time.monotonic()
        try:
            text, tokens = self._call(prompt, temperature=temperature)
        except Exception as exc:  # noqa: BLE001 — any failure degrades, never raises upstream
            logger.warning("%s call failed (%s): %s", type(self).__name__, kind, exc)
            return AIResult(status="error", kind=kind, model=self.model_id, error=str(exc))
        latency = int((time.monotonic() - started) * 1000)
        parsed = self._parse_json(text, prefer_keys)
        if parsed is None:
            logger.warning("%s returned unparseable output for %s", type(self).__name__, kind)
            return AIResult(status="unknown", kind=kind, model=self.model_id,
                            latency_ms=latency, tokens=tokens, error="Unparseable model output")
        assumptions = parsed.pop("assumptions", None) or []
        if not isinstance(assumptions, list):
            assumptions = [str(assumptions)]
        return AIResult(status="ok", kind=kind, model=self.model_id, output=parsed,
                        assumptions=[str(a) for a in assumptions], latency_ms=latency, tokens=tokens)

    # ---- public API (identical across models) ----

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
