"""Selects the AI implementation from configuration.

Live Gemma when GEMINI_API_KEY is set; otherwise the null service (never fabricates).
The model id is env-driven (`AI_MODEL`) so the backing model is flippable.
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.services.ai.base import AIService, NullAIService


@lru_cache
def get_ai_service() -> AIService:
    if settings.GEMINI_API_KEY:
        # Imported lazily so the null path has no httpx-call surface.
        from app.services.ai.gemma import GemmaAIService

        return GemmaAIService(settings.GEMINI_API_KEY, settings.AI_MODEL)
    return NullAIService()
