"""AI service package — all Gemma/Gemini calls funnel through here.

`AIService` is the swappable contract; `NullAIService` returns "unknown" rather
than fabricating; `GemmaAIService` is the live Gemma 3 27B implementation (via
Google's Generative Language API). `get_ai_service()` picks the right one from env.
"""
from app.services.ai.base import AIResult, AIService, NullAIService
from app.services.ai.factory import get_ai_service

__all__ = ["AIService", "NullAIService", "AIResult", "get_ai_service"]
