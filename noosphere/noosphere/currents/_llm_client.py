"""Thin wrapper over `noosphere.llm` for the currents subsystem.

Provides a ``make_client()`` factory (used by prompts 06/17 as a monkeypatch
seam so the scheduler/integration tests can inject a stub without touching
``noosphere.llm`` directly), plus a ``chat_json`` helper that prompts 05/06/17
call for a single-shot completion.

We deliberately DO NOT add a new Anthropic SDK call site: everything routes
through ``noosphere.llm.LLMClient`` so there is exactly one place that holds
real credentials.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from noosphere.llm import LLMClient, llm_client_from_settings


@dataclass(frozen=True)
class LLMReply:
    text: str
    tokens_prompt: int
    tokens_completion: int
    model: str
    stop_reason: str = "end_turn"


class LLMError(RuntimeError):
    """Wraps provider errors from the underlying LLMClient."""


def make_client() -> LLMClient:
    """Factory seam: prompt 17 monkeypatches this to inject a stub client."""
    return llm_client_from_settings()


def estimate_tokens(text: str) -> int:
    """Cheap char/4 heuristic. Only the hourly ceiling cares about precision."""
    return max(1, len(text) // 4)


def chat_json(
    *,
    system: str,
    user: str,
    model: str = "claude-haiku-4-5",
    max_tokens: int = 900,
    api_key: Optional[str] = None,  # accepted for API parity; underlying client reads from settings
    client: Optional[LLMClient] = None,
) -> LLMReply:
    """Single-shot completion. Returns the assistant text in an LLMReply.

    The underlying ``noosphere.llm.LLMClient.complete`` returns just the text;
    token counts are not exposed. We provide best-effort estimates via a
    ``char/4`` heuristic so the budget guard can operate. This is deliberately
    approximate — the only precision that matters is the hourly ceiling.
    """
    try:
        c = client or make_client()
        text = c.complete(
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=0.0,
        )
    except Exception as e:  # noqa: BLE001 — wrap provider-specific errors
        raise LLMError(f"{type(e).__name__}: {e}") from e

    return LLMReply(
        text=text,
        tokens_prompt=estimate_tokens(system) + estimate_tokens(user),
        tokens_completion=estimate_tokens(text),
        model=model,
        stop_reason="end_turn",
    )


@dataclass(frozen=True)
class LLMStreamChunk:
    text_delta: str
    tokens_prompt_so_far: int
    tokens_completion_so_far: int


async def chat_stream_text(
    *,
    system: str,
    user: str,
    model: str = "claude-haiku-4-5",
    max_tokens: int = 600,
    api_key: Optional[str] = None,  # accepted for API parity
    client: Optional[LLMClient] = None,
) -> AsyncIterator[LLMStreamChunk]:
    """Async generator yielding text deltas.

    The underlying ``noosphere.llm.LLMClient`` has no native streaming method,
    so we simulate streaming by calling ``.complete()`` once and yielding
    fixed-size text slices. This preserves the ``AsyncIterator`` contract for
    the follow-up UI and for tests. When the underlying client gains real
    SSE support, swap the body — the return type is stable.
    """
    c = client or make_client()
    try:
        text = await asyncio.to_thread(
            c.complete,
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=0.0,
        )
    except Exception as e:  # noqa: BLE001 — wrap provider-specific errors
        raise LLMError(f"{type(e).__name__}: {e}") from e

    total_prompt = max(1, (len(system) + len(user)) // 4)
    step = 80
    emitted = 0
    if not text:
        # Still emit a single empty chunk so downstream consumers see at least
        # one iteration before done.
        yield LLMStreamChunk(
            text_delta="",
            tokens_prompt_so_far=total_prompt,
            tokens_completion_so_far=1,
        )
        return
    for i in range(0, len(text), step):
        chunk = text[i : i + step]
        emitted += len(chunk)
        yield LLMStreamChunk(
            text_delta=chunk,
            tokens_prompt_so_far=total_prompt,
            tokens_completion_so_far=max(1, emitted // 4),
        )
