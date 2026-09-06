"""AIService contract + the null (disabled) implementation.

Every method returns an `AIResult`: a uniform envelope carrying the structured
`output`, a `status` ("ok" | "unknown" | "error"), the model used, latency, any
`assumptions` the model flagged, and (on failure) an `error`. Callers persist an
`AIGeneration` audit row from this envelope; the model output itself never decides
whether an outbound send happens — `can_send` still governs that.

Guardrail: on any uncertainty or failure the service returns `status="unknown"`
with empty/None output rather than fabricating.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIResult:
    """Uniform envelope for every AI call."""

    status: str = "unknown"          # ok | unknown | error
    output: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    kind: str | None = None
    assumptions: list[str] = field(default_factory=list)
    latency_ms: int | None = None
    tokens: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class AIService(ABC):
    """All Gemma calls go through this seam so the backing model is swappable."""

    model_id: str = "none"

    @property
    def enabled(self) -> bool:
        return False

    @abstractmethod
    def qualify_lead(self, lead: dict[str, Any], icp: dict[str, Any] | None = None) -> AIResult: ...

    @abstractmethod
    def generate_email(self, lead: dict[str, Any], context: dict[str, Any] | None = None) -> AIResult: ...

    @abstractmethod
    def generate_linkedin_message(self, lead: dict[str, Any], context: dict[str, Any] | None = None) -> AIResult: ...

    @abstractmethod
    def generate_follow_up(self, thread: list[dict[str, Any]], context: dict[str, Any] | None = None) -> AIResult: ...

    @abstractmethod
    def classify_reply(self, message: str, context: dict[str, Any] | None = None) -> AIResult: ...

    @abstractmethod
    def summarize_conversation(self, thread: list[dict[str, Any]]) -> AIResult: ...

    @abstractmethod
    def recommend_next_action(self, lead: dict[str, Any], context: dict[str, Any] | None = None) -> AIResult: ...

    @abstractmethod
    def analyze_campaign(self, stats: dict[str, Any]) -> AIResult: ...

    @abstractmethod
    def nl_to_filters(self, query: str, schema: dict[str, Any] | None = None) -> AIResult: ...

    @abstractmethod
    def copilot(self, question: str, context: dict[str, Any] | None = None) -> AIResult: ...


class NullAIService(AIService):
    """No-op implementation used when no API key is configured. Never fabricates."""

    model_id = "none"

    def _unknown(self, kind: str, output: dict[str, Any] | None = None) -> AIResult:
        return AIResult(
            status="unknown",
            kind=kind,
            output=output or {},
            model=None,
            error="AI is not configured (set GEMINI_API_KEY).",
        )

    def qualify_lead(self, lead, icp=None):
        return self._unknown("qualify_lead", {"score": None, "verdict": "unknown", "rationale": None, "signals": []})

    def generate_email(self, lead, context=None):
        return self._unknown("generate_email", {"subject": None, "body": None})

    def generate_linkedin_message(self, lead, context=None):
        return self._unknown("generate_linkedin_message", {"body": None})

    def generate_follow_up(self, thread, context=None):
        return self._unknown("generate_follow_up", {"subject": None, "body": None})

    def classify_reply(self, message, context=None):
        return self._unknown("classify_reply", {"intent": "unknown", "sentiment": "unknown", "confidence": None})

    def summarize_conversation(self, thread):
        return self._unknown("summarize_conversation", {"summary": None, "next_action": None})

    def recommend_next_action(self, lead, context=None):
        return self._unknown("recommend_next_action", {"action": None, "rationale": None})

    def analyze_campaign(self, stats):
        return self._unknown("analyze_campaign", {"summary": None, "strengths": [], "issues": [], "recommendations": []})

    def nl_to_filters(self, query, schema=None):
        return self._unknown("nl_to_filters", {"match": "all", "conditions": [], "sort_by": "created_at", "sort_dir": "desc"})

    def copilot(self, question, context=None):
        return self._unknown("copilot", {"answer": None})
