"""Scripted stand-in for ``noosphere.llm.LLMClient``.

Used by prompt-17 end-to-end and regression tests to replace the real
Anthropic-backed client without touching the network. Install via::

    from tests.fakes.fake_anthropic_client import FakeLLMClient
    fake = FakeLLMClient(script=[...])
    monkeypatch.setattr(
        "noosphere.currents._llm_client.make_client",
        lambda: fake,
    )

The ``LLMClient`` Protocol that noosphere expects has a single method,
``complete(system, user, max_tokens, temperature) -> str``. ``FakeLLMClient``
matches that shape and records every call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class FakeLLMClient:
    """Scripted replacement for ``noosphere.llm.LLMClient``.

    Each item in ``script`` is a callable that receives a kwargs dict
    (``system``, ``user``, ``max_tokens``, ``temperature``) and returns the
    response string. Items are consumed one per ``.complete()`` call. The
    call log on ``.calls`` is append-only so tests can assert on exact
    prompt text.
    """

    script: list[Callable[[dict], str]] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        kwargs = {
            "system": system,
            "user": user,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError(
                "FakeLLMClient: unexpected .complete() call, script empty"
            )
        reply = self.script.pop(0)
        return reply(kwargs)


def reply_with(text: str) -> Callable[[dict], str]:
    """Convenience: return a script entry that always yields ``text``."""

    def _reply(_kwargs: dict) -> str:  # noqa: ARG001
        return text

    return _reply
