"""Live DeepSeek implementation via an OpenAI-compatible chat-completions endpoint.

Default transport is NVIDIA's inference API (`https://integrate.api.nvidia.com/v1`),
which is what the `openai` SDK talks to under the hood — we use `httpx` directly to
keep the same stub-in-tests seam as every other AI service and add no dependency.

Only the transport lives here; JSON extraction, per-task config and guardrails are
shared in `JsonModelService`. `thinking` is disabled so the model returns the JSON
object directly (faster, cheaper, no scratchpad to parse around); the shared parser
still strips any stray `<think>` block as a safety net.
"""
from __future__ import annotations

import httpx

from app.services.ai.json_model import JsonModelService

_SYSTEM = (
    "You are a precise B2B sales assistant. Respond with ONLY a single JSON object — "
    "no prose, no markdown, no code fences, nothing before or after it."
)


class DeepSeekAIService(JsonModelService):
    def __init__(self, api_key: str, model_id: str, base_url: str,
                 timeout: float = 60.0) -> None:
        self._api_key = api_key
        self.model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _post(self, payload: dict) -> httpx.Response:
        return httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
            timeout=self._timeout,
        )

    def _call(self, prompt: str, *, temperature: float = 0.4, max_tokens: int = 4096) -> tuple[str, int | None]:
        """Return (text, token_count). Raises on transport/HTTP error."""
        payload: dict = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "top_p": 0.95,
            "max_tokens": max_tokens,
            "stream": False,
            # DeepSeek chat template: skip the reasoning trace, answer directly.
            "chat_template_kwargs": {"thinking": False},
            "response_format": {"type": "json_object"},
        }
        resp = self._post(payload)
        # Some OpenAI-compatible servers reject the optional knobs — retry once plain.
        if resp.status_code in (400, 422):
            payload.pop("chat_template_kwargs", None)
            payload.pop("response_format", None)
            resp = self._post(payload)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("No choices in response")
        msg = choices[0].get("message", {}) or {}
        text = msg.get("content") or ""
        # Reasoning models may put the trace in a sibling field; the answer is `content`.
        if not text and msg.get("reasoning_content"):
            text = msg["reasoning_content"]
        tokens = (data.get("usage") or {}).get("total_tokens")
        return text, tokens
