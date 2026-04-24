"""LLM client abstraction."""

from __future__ import annotations

import pytest

from noosphere.llm import MockLLMClient


def test_mock_llm_records_calls_and_returns_scripted() -> None:
    m = MockLLMClient(
        responses=["hello", "world"],
        prompt_must_contain=("alpha",),
    )
    assert (
        m.complete(system="alpha", user="beta", max_tokens=10)
        == "hello"
    )
    assert m.complete(system="alpha", user="gamma", max_tokens=10) == "world"
    assert len(m.calls) == 2
    assert m.calls[0]["user"] == "beta"


def test_mock_llm_asserts_prompt_structure() -> None:
    m = MockLLMClient(responses=["x"], prompt_must_contain=("needle",))
    with pytest.raises(AssertionError):  # noqa: PT012 — explicit check
        m.complete(system="s", user="haystack", max_tokens=5)
