"""AI service package — every model call funnels through here.

`AIService` is the swappable contract; `NullAIService` returns "unknown" rather
than fabricating; `JsonModelService` holds the shared JSON parsing + guardrails;
`DeepSeekAIService` (OpenAI-compatible, default) and `GemmaAIService` (Google
Generative Language API) are the live implementations. `get_ai_service()` picks
one from env (`AI_PROVIDER`).
"""
from app.services.ai.base import AIResult, AIService, NullAIService
from app.services.ai.factory import get_ai_service

__all__ = ["AIService", "NullAIService", "AIResult", "get_ai_service"]
