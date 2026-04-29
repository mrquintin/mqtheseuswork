"""Anthropic Haiku client seam for Currents opinion and follow-up calls."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import AsyncIterator, Literal, Protocol


DEFAULT_HAIKU_MODEL = "claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = DEFAULT_HAIKU_MODEL


@dataclass(frozen=True)
class LLMStreamChunk:
    kind: Literal["token", "done"]
    text: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = DEFAULT_HAIKU_MODEL


class AnthropicLike(Protocol):
    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse: ...

    async def stream(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[LLMStreamChunk]: ...


def _anthropic_api_key() -> str:
    try:
        from noosphere.config import get_settings

        settings = get_settings()
        if getattr(settings, "llm_provider", "") == "anthropic" and settings.llm_api_key:
            return settings.llm_api_key
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _haiku_model() -> str:
    return os.environ.get("CURRENTS_HAIKU_MODEL", DEFAULT_HAIKU_MODEL)


class AnthropicHaikuClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        from anthropic import AsyncAnthropic

        self._model = model
        self._client = AsyncAnthropic(api_key=api_key or "")

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        usage = getattr(message, "usage", None)
        return LLMResponse(
            text="".join(parts),
            prompt_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            model=self._model,
        )

    async def stream(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[LLMStreamChunk]:
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                yield LLMStreamChunk(kind="token", text=text, model=self._model)
            final_message = await stream.get_final_message()
        usage = getattr(final_message, "usage", None)
        yield LLMStreamChunk(
            kind="done",
            prompt_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            model=self._model,
        )


def make_client() -> AnthropicLike:
    """Factory kept as the test/e2e replacement seam."""
    return AnthropicHaikuClient(api_key=_anthropic_api_key(), model=_haiku_model())
