"""Selects the AI implementation from configuration.

`AI_PROVIDER`:
  - "auto"     → DeepSeek if NVIDIA_API_KEY set, else Gemma if GEMINI_API_KEY set, else null
  - "deepseek" → DeepSeek (NVIDIA_API_KEY); null if the key is missing
  - "gemma"    → Gemma (GEMINI_API_KEY); null if the key is missing
  - "null"     → the null service (never fabricates)

Concrete services are imported lazily so the null path keeps no httpx-call surface.
Model ids are env-driven (`DEEPSEEK_MODEL` / `AI_MODEL`).
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.services.ai.base import AIService, NullAIService


def _deepseek() -> AIService | None:
    if not settings.NVIDIA_API_KEY:
        return None
    from app.services.ai.deepseek import DeepSeekAIService

    return DeepSeekAIService(
        settings.NVIDIA_API_KEY, settings.DEEPSEEK_MODEL, settings.AI_BASE_URL
    )


def _gemma() -> AIService | None:
    if not settings.GEMINI_API_KEY:
        return None
    from app.services.ai.gemma import GemmaAIService

    return GemmaAIService(settings.GEMINI_API_KEY, settings.AI_MODEL)


@lru_cache
def get_ai_service() -> AIService:
    provider = (settings.AI_PROVIDER or "auto").lower()
    if provider == "deepseek":
        return _deepseek() or NullAIService()
    if provider == "gemma":
        return _gemma() or NullAIService()
    if provider == "null":
        return NullAIService()
    # auto
    return _deepseek() or _gemma() or NullAIService()
