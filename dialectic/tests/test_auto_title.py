"""Tests for ``dialectic.auto_title``.

The LLM call is the only side-effect: we monkeypatch
``dialectic.auto_title._create_client`` so tests never actually call
Anthropic. A gated real-call test (``DIALECTIC_TEST_REAL_TITLE=1``)
exists for manual validation against the live Haiku endpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

import dialectic.auto_title as auto_title_mod
from dialectic.auto_title import AutoTitleResult, generate_title
from dialectic.config import AutoTitleConfig


# ---------------------------------------------------------------------------
# Fake Anthropic client scaffolding
# ---------------------------------------------------------------------------


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeResponse:
    content: list


class _FakeMessages:
    def __init__(self, behavior, shared_calls):
        self._behavior = behavior
        self.calls = shared_calls

    def create(self, **kwargs):
        self.calls.append(kwargs)
        value = self._behavior(len(self.calls))
        if isinstance(value, BaseException):
            raise value
        return _FakeResponse(content=[_FakeTextBlock(text=value)])


class _FakeClient:
    def __init__(self, behavior, shared_calls):
        self.messages = _FakeMessages(behavior, shared_calls)


def _install_client(monkeypatch, behavior):
    """Install a fake Anthropic client. ``behavior`` is a callable
    ``(attempt_number) -> str | Exception`` that decides what each call
    returns or raises. Attempts are 1-indexed and counted across every
    retry (``_create_client`` is called fresh per attempt, so the call
    log is shared via the holder to avoid resetting on each retry)."""
    holder: dict = {"calls": []}

    def factory(api_key):
        client = _FakeClient(behavior, holder["calls"])
        holder["client"] = client
        return client

    monkeypatch.setattr(auto_title_mod, "_create_client", factory)
    return holder


def _cfg(**overrides) -> AutoTitleConfig:
    base = dict(
        anthropic_key="test-key",
        max_retries=2,
        retry_backoff_seconds=0.0,
    )
    base.update(overrides)
    return AutoTitleConfig(**base)


_REAL_TRANSCRIPT = (
    "So the question I keep coming back to is: what is the school actually "
    "for? We keep talking about programs and curriculum but the purpose "
    "itself is unclear. If the school exists to produce founders who can "
    "think clearly under pressure, that implies one design. If it exists "
    "to preserve a particular methodology across generations, that implies "
    "a very different institution. We should pick the purpose first, and "
    "everything else follows from that."
) * 2  # >= 200 chars


# ---------------------------------------------------------------------------
# Short / empty transcript paths
# ---------------------------------------------------------------------------


def test_empty_transcript_returns_fallback(monkeypatch):
    # LLM should not be called at all for an empty transcript.
    called = {"n": 0}

    def factory(api_key):
        called["n"] += 1
        raise AssertionError("LLM must not be called for short transcript")

    monkeypatch.setattr(auto_title_mod, "_create_client", factory)

    r = generate_title("", duration_seconds=0.0, cfg=_cfg())
    assert r.method == "fallback"
    assert r.title.startswith("Dialectic session — ")
    assert r.recorded_date  # ISO date stamped
    assert called["n"] == 0


def test_short_transcript_returns_fallback(monkeypatch):
    def factory(api_key):
        raise AssertionError("LLM must not be called for short transcript")

    monkeypatch.setattr(auto_title_mod, "_create_client", factory)

    r = generate_title("hi " * 10, duration_seconds=120.0, cfg=_cfg())
    assert r.method == "fallback"
    assert "0h 02m" in r.title or "2m" in r.title


# ---------------------------------------------------------------------------
# LLM happy path
# ---------------------------------------------------------------------------


def test_llm_happy_path(monkeypatch):
    _install_client(monkeypatch, lambda n: "The Purpose of the School")

    r = generate_title(_REAL_TRANSCRIPT, 1800.0, cfg=_cfg())
    assert r.method == "llm"
    assert r.title == "The Purpose of the School"
    assert r.warnings == []


def test_llm_strips_trailing_period_and_quotes(monkeypatch):
    _install_client(monkeypatch, lambda n: '"The Purpose of the School."')

    r = generate_title(_REAL_TRANSCRIPT, 1800.0, cfg=_cfg())
    assert r.method == "llm"
    assert r.title == "The Purpose of the School"


def test_llm_truncates_overlong_title(monkeypatch):
    overlong = "A " * 60  # 120 chars of "A A A ..."
    _install_client(monkeypatch, lambda n: overlong)

    r = generate_title(_REAL_TRANSCRIPT, 1800.0, cfg=_cfg())
    assert r.method == "llm"
    assert len(r.title) <= 70
    assert r.title.endswith("…")
    assert any("exceeded 70 chars" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# LLM failure / retry paths
# ---------------------------------------------------------------------------


def test_llm_retries_then_succeeds(monkeypatch):
    import anthropic

    def behavior(attempt):
        if attempt <= 2:
            # APIConnectionError takes a `request` kwarg in the 0.x SDK;
            # the constructor accepts None for our purposes.
            return anthropic.APIConnectionError(request=None)  # type: ignore[arg-type]
        return "Charter Language for the Advisory Board"

    _install_client(monkeypatch, behavior)
    r = generate_title(_REAL_TRANSCRIPT, 1800.0, cfg=_cfg())
    assert r.method == "llm"
    assert r.title == "Charter Language for the Advisory Board"
    # Two retry warnings were recorded, then success.
    retry_warnings = [w for w in r.warnings if "attempt" in w]
    assert len(retry_warnings) == 2


def test_llm_always_fails_returns_fallback(monkeypatch):
    import anthropic

    def behavior(attempt):
        return anthropic.APIConnectionError(request=None)  # type: ignore[arg-type]

    _install_client(monkeypatch, behavior)
    r = generate_title(_REAL_TRANSCRIPT, 3600.0, cfg=_cfg())
    assert r.method == "fallback"
    assert r.title.startswith("Dialectic session — ")
    # max_retries=2 → 3 total attempts, 3 warnings.
    retry_warnings = [w for w in r.warnings if "attempt" in w]
    assert len(retry_warnings) == 3


def test_llm_insufficient_content_marker_returns_fallback(monkeypatch):
    _install_client(monkeypatch, lambda n: "INSUFFICIENT_CONTENT")

    r = generate_title(_REAL_TRANSCRIPT, 0.0, cfg=_cfg())
    assert r.method == "fallback"
    assert any("insufficient content" in w for w in r.warnings)


def test_llm_empty_response_returns_fallback(monkeypatch):
    _install_client(monkeypatch, lambda n: "")

    r = generate_title(_REAL_TRANSCRIPT, 0.0, cfg=_cfg())
    assert r.method == "fallback"


# ---------------------------------------------------------------------------
# Config + transcript-trim behavior
# ---------------------------------------------------------------------------


def test_no_api_key_returns_fallback(monkeypatch):
    def factory(api_key):
        raise AssertionError("LLM must not be called without an API key")

    monkeypatch.setattr(auto_title_mod, "_create_client", factory)

    r = generate_title(_REAL_TRANSCRIPT, 1800.0, cfg=_cfg(anthropic_key=""))
    assert r.method == "fallback"
    assert any("ANTHROPIC_API_KEY" in w for w in r.warnings)


def test_long_transcript_is_truncated_before_sending(monkeypatch):
    holder = _install_client(monkeypatch, lambda n: "A Good Title")

    giant = "word " * 5000  # ~25_000 chars
    r = generate_title(giant, 3600.0, cfg=_cfg(max_transcript_chars_for_title=1000))
    assert r.method == "llm"

    # Inspect what the fake client saw — the user content must be <= cap
    # (plus the "Transcript:\n\n" prefix).
    call = holder["calls"][0]
    user_content = call["messages"][0]["content"]
    assert user_content.startswith("Transcript:\n\n")
    body = user_content[len("Transcript:\n\n"):]
    assert len(body) <= 1000


def test_deterministic_fallback_format():
    from dialectic.auto_title import _deterministic_fallback

    # Sub-hour → "Mm"
    assert "12m" in _deterministic_fallback(12 * 60)
    # Multi-hour → "Hh MMm"
    assert "2h 05m" in _deterministic_fallback(2 * 3600 + 5 * 60)
    # Zero → "0m"
    assert "0m" in _deterministic_fallback(0)


# ---------------------------------------------------------------------------
# Gated real-LLM smoke
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("DIALECTIC_TEST_REAL_TITLE") != "1",
    reason="set DIALECTIC_TEST_REAL_TITLE=1 for real Haiku call",
)
def test_real_haiku_call():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    r = generate_title(_REAL_TRANSCRIPT, 1800.0)
    assert r.method == "llm"
    assert 3 <= len(r.title.split()) <= 12
    assert len(r.title) <= 70
    assert not r.title.endswith(".")
    print(f"\n[real-haiku] title={r.title!r} warnings={r.warnings}")
