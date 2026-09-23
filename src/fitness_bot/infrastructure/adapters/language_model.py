from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from fitness_bot.service.ports.language_model import LanguageModel

logger = logging.getLogger(__name__)

# Timeweb Cloud OpenAI-compatible DeepSeek V4 Flash (simpler of the two DeepSeek SKUs).
DEFAULT_TIMEWEB_MODEL = "deepseek-v4-flash"
# AI Gateway OpenAI-compatible root (docs: https://timeweb.cloud/docs/ai-agents/api-usage/ai-gateway).
DEFAULT_TIMEWEB_BASE_URL = "https://api.timeweb.ai/v1"
_CHAT_COMPLETIONS_SUFFIX = "/chat/completions"


def normalize_openai_compatible_root(base_url: str) -> str:
    """Return OpenAI-compatible API root without a trailing /chat/completions.

    Callers (and OpenAI SDK) append /chat/completions themselves. Accepting a full
    completions URL in TIMEWEB_BASE_URL would otherwise 404 or double the path.
    """
    root = base_url.strip().rstrip("/")
    if root.endswith(_CHAT_COMPLETIONS_SUFFIX):
        root = root[: -len(_CHAT_COMPLETIONS_SUFFIX)].rstrip("/")
    return root


def _message_body(*, system: str, user: str, model: str, temperature: float, stream: bool) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": temperature,
        "stream": stream,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }


def _content_from_chunk(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    return str(content) if content else ""


class StubLanguageModel(LanguageModel):
    async def complete(self, *, system: str, user: str) -> str:
        raise NotImplementedError("LanguageModel adapter is not configured")


class TimewebLanguageModel(LanguageModel):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = DEFAULT_TIMEWEB_MODEL,
        temperature: float = 0.2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("TIMEWEB_API_KEY is required for LanguageModel")
        if not base_url.strip():
            raise ValueError("TIMEWEB_BASE_URL is required for LanguageModel")
        self._api_key = api_key
        self._base_url = normalize_openai_compatible_root(base_url)
        if not self._base_url:
            raise ValueError("TIMEWEB_BASE_URL is required for LanguageModel")
        self._model = model
        self._temperature = temperature
        self._client = client
        self._owns_client = client is None

    @property
    def chat_completions_url(self) -> str:
        return f"{self._base_url}{_CHAT_COMPLETIONS_SUFFIX}"

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def complete(self, *, system: str, user: str) -> str:
        parts: list[str] = []
        async for chunk in self.stream(system=system, user=user):
            parts.append(chunk)
        text = "".join(parts)
        if not text:
            raise ValueError("LanguageModel returned empty content")
        return text

    async def stream(self, *, system: str, user: str) -> AsyncIterator[str]:
        client = await self._http()
        body = _message_body(
            system=system,
            user=user,
            model=self._model,
            temperature=self._temperature,
            stream=True,
        )
        async with client.stream(
            "POST",
            self.chat_completions_url,
            headers=self._headers(),
            json=body,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    logger.debug("skip non-json sse chunk: %s", data[:120])
                    continue
                content = _content_from_chunk(payload)
                if content:
                    yield content
