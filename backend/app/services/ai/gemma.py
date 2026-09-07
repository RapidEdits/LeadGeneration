"""Live Gemma implementation via Google's Generative Language API.

Only the transport lives here — the JSON extraction, per-task config, and
guardrails are shared in `JsonModelService`. One HTTP call per task (`_call`),
isolated so tests can stub it without a network.
"""
from __future__ import annotations

import httpx

from app.services.ai.json_model import JsonModelService

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GemmaAIService(JsonModelService):
    def __init__(self, api_key: str, model_id: str, timeout: float = 45.0) -> None:
        self._api_key = api_key
        self.model_id = model_id
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

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
        resp = httpx.post(url, params={"key": self._api_key}, json=payload, timeout=self._timeout)
        # Some Gemma models on the API reject responseMimeType — retry once without it.
        if resp.status_code == 400 and "responseMimeType" in resp.text:
            payload["generationConfig"].pop("responseMimeType", None)
            resp = httpx.post(url, params={"key": self._api_key}, json=payload, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("No candidates in response")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        tokens = (data.get("usageMetadata") or {}).get("totalTokenCount")
        return text, tokens
