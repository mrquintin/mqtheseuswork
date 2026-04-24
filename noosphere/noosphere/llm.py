"""
Injectable LLM clients (Anthropic, OpenAI, mock). No direct SDK calls elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str: ...


class AnthropicLLMClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        from anthropic import Anthropic

        self._model = model
        self._client = Anthropic(api_key=api_key or "")

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts: list[str] = []
        for block in msg.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "".join(parts)


class OpenAILLMClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._model = model
        self._client = OpenAI(api_key=api_key or "")

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        choice = resp.choices[0].message
        return (choice.content or "").strip()


@dataclass
class MockLLMClient:
    """Returns scripted text; records prompts for assertions."""

    responses: list[str]
    calls: list[dict[str, Any]] = field(default_factory=list)
    prompt_must_contain: tuple[str, ...] = ()

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        for needle in self.prompt_must_contain:
            if needle not in system and needle not in user:
                raise AssertionError(f"mock LLM: expected prompt to contain {needle!r}")
        self.calls.append(
            {
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if not self.responses:
            return ""
        return self.responses.pop(0)


def llm_client_from_settings() -> LLMClient:
    """Factory using `noosphere.config.get_settings()`.

    Reads the *effective* provider/model/key from settings, which respects
    the operator's preference but auto-falls-back to whichever provider
    actually has credentials in the environment. This is what lets the
    GitHub Actions workflow work with only ``OPENAI_API_KEY`` set — the
    default preference is ``anthropic``, but the effective provider flips
    to ``openai`` when Anthropic's env var is empty.
    """
    from noosphere.config import get_settings

    s = get_settings()
    provider = s.effective_llm_provider()
    key = s.effective_llm_api_key()
    model = s.effective_llm_model()
    if provider == "openai":
        return OpenAILLMClient(api_key=key, model=model)
    return AnthropicLLMClient(api_key=key, model=model)
