"""Test-only Anthropic-like client for Currents opinion and follow-up tests."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from noosphere.currents._llm_client import LLMResponse, LLMStreamChunk


ScriptItem = (
    LLMResponse
    | str
    | Mapping[str, Any]
    | Callable[[dict[str, Any]], LLMResponse | str | Mapping[str, Any]]
)

VALID_PIPELINE_QUOTED_SPAN = "durable compounding depends on disciplined evidence"


def _first_source_id(prompt: str) -> str:
    match = re.search(r"source_kind:\s*conclusion\s*\nsource_id:\s*([^\n]+)", prompt)
    if match:
        return match.group(1).strip()
    match = re.search(r"source_id:\s*([^\n]+)", prompt)
    return match.group(1).strip() if match else "conclusion_pipeline_a"


def _coerce_response(item: ScriptItem, call: dict[str, Any]) -> LLMResponse:
    if callable(item):
        item = item(call)
    if isinstance(item, LLMResponse):
        return item
    if isinstance(item, str):
        return LLMResponse(text=item, prompt_tokens=100, completion_tokens=25)
    if "text" in item:
        return LLMResponse(
            text=str(item["text"]),
            prompt_tokens=int(item.get("prompt_tokens", 100) or 0),
            completion_tokens=int(item.get("completion_tokens", 25) or 0),
            model=str(item.get("model", "claude-haiku-4-5-test")),
        )
    return LLMResponse(
        text=json.dumps(dict(item)),
        prompt_tokens=100,
        completion_tokens=25,
        model="claude-haiku-4-5-test",
    )


def opine_with_valid_citation(call: dict[str, Any]) -> LLMResponse:
    """Return a strict opinion JSON citing the first retrieved conclusion."""

    source_id = _first_source_id(str(call.get("user", "")))
    return LLMResponse(
        text=json.dumps(
            {
                "stance": "COMPLICATES",
                "confidence": 0.78,
                "headline": "The event complicates a compounding thesis",
                "body_markdown": (
                    "The event is worth treating as a test of the firm's stored "
                    "view, but the cited source supports a narrow conclusion."
                ),
                "uncertainty_notes": ["This is grounded in retrieved conclusions."],
                "citations": [
                    {
                        "source_kind": "conclusion",
                        "source_id": source_id,
                        "quoted_span": VALID_PIPELINE_QUOTED_SPAN,
                    }
                ],
                "topic_hint": "markets",
            }
        ),
        prompt_tokens=240,
        completion_tokens=90,
        model="claude-haiku-4-5-test",
    )


class FakeAnthropicClient:
    """Anthropic-like fake that records prompts and consumes scripted responses."""

    def __init__(self, script: list[ScriptItem]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        call = {
            "system": system,
            "user": user,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        self.calls.append(call)
        if not self.script:
            raise AssertionError("no scripted Anthropic response left")
        return _coerce_response(self.script.pop(0), call)

    async def stream(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float = 0.0,
    ):
        response = await self.complete(
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        yield LLMStreamChunk(kind="token", text=response.text, model=response.model)
        yield LLMStreamChunk(
            kind="done",
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            model=response.model,
        )
