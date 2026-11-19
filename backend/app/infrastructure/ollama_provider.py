"""Ollama adapter implementing the domain ``LLMProvider`` port.

Uses httpx to call the local Ollama HTTP API. Transport failures are translated
into domain errors so the application and presentation layers stay agnostic of
httpx. No model-family-specific prompts or stop tokens are used here.
"""

from __future__ import annotations

import httpx

from domain.errors import LLMProviderError, LLMUnreachableError, LLMTimedOutError
from domain.ports import LLMProvider


class OllamaLLMProvider:
    """Concrete LLM provider backed by a local Ollama server.

    The model is configurable via ``OLLAMA_MODEL``; swapping to gemma2,
    deepseek-r1, llama3.1, or any other Ollama model requires no code changes.
    """

    def __init__(self, base_url: str, model: str, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    @property
    def model(self) -> str:
        """Identifier of the configured Ollama model."""
        return self._model

    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Generate a completion via ``POST /api/generate``."""
        payload: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if system:
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/generate", json=payload
                )
        except httpx.ConnectError as exc:
            raise LLMUnreachableError(self._base_url) from exc
        except httpx.TimeoutException as exc:
            raise LLMTimedOutError(self._timeout) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"LLM provider HTTP error: {exc}") from exc

        if response.status_code >= 400:
            raise LLMProviderError(
                f"LLM provider returned HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderError("LLM provider returned invalid JSON") from exc

        return str(data.get("response", "") or "")
