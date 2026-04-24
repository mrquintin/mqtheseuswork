"""Post-recording auto-title via Claude Haiku.

Generates a short, content-reflective title for a completed Dialectic
recording. On any failure (no API key, rate-limit, malformed response,
transcript too short) falls back deterministically to a date-and-duration
string. Title generation never fails the pipeline — a bad title is less
bad than a lost recording.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dialectic.config import AutoTitleConfig

log = logging.getLogger(__name__)

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "_prompts" / "auto_title_system.md"
_MIN_TRANSCRIPT_CHARS = 200
_MAX_TITLE_CHARS = 70


@dataclass(frozen=True)
class AutoTitleResult:
    title: str
    recorded_date: str  # ISO date (YYYY-MM-DD), UTC
    method: Literal["llm", "fallback"]
    warnings: list[str] = field(default_factory=list)


def _deterministic_fallback(duration_seconds: float) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seconds = max(0, int(duration_seconds or 0))
    hrs, rem = divmod(seconds, 3600)
    mins, _ = divmod(rem, 60)
    dur = f"{hrs}h {mins:02d}m" if hrs else f"{mins}m"
    return f"Dialectic session — {now} ({dur})"


def _create_client(api_key: str):
    """Build an Anthropic client. Separate function so tests can
    monkeypatch this seam without importing anthropic themselves."""
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def _extract_text(resp) -> str:
    """Pull the text out of an Anthropic messages response, tolerant of
    the SDK's content-block shape."""
    parts: list[str] = []
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", "") == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts)


def _clean_title(raw: str) -> str:
    return raw.strip().strip('"').strip("'").rstrip(".").strip()


def generate_title(
    transcript: str,
    duration_seconds: float,
    cfg: AutoTitleConfig | None = None,
) -> AutoTitleResult:
    cfg = cfg or AutoTitleConfig()
    warnings: list[str] = []
    recorded_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    text = (transcript or "").strip()
    if len(text) < _MIN_TRANSCRIPT_CHARS:
        warnings.append("transcript too short for a meaningful LLM title")
        return AutoTitleResult(
            title=_deterministic_fallback(duration_seconds),
            recorded_date=recorded_date,
            method="fallback",
            warnings=warnings,
        )

    if not cfg.anthropic_key:
        warnings.append("no ANTHROPIC_API_KEY configured")
        return AutoTitleResult(
            title=_deterministic_fallback(duration_seconds),
            recorded_date=recorded_date,
            method="fallback",
            warnings=warnings,
        )

    if len(text) > cfg.max_transcript_chars_for_title:
        # First 5-10 min of a 2h session is where the topic is named;
        # the tail is usually branchy exploration. Use the head only.
        text = text[: cfg.max_transcript_chars_for_title]

    try:
        system_prompt = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as e:
        warnings.append(f"system prompt unreadable: {e}")
        return AutoTitleResult(
            title=_deterministic_fallback(duration_seconds),
            recorded_date=recorded_date,
            method="fallback",
            warnings=warnings,
        )

    for attempt in range(cfg.max_retries + 1):
        try:
            client = _create_client(cfg.anthropic_key)
            resp = client.messages.create(
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": f"Transcript:\n\n{text}"}
                ],
            )
            raw = _clean_title(_extract_text(resp))
            if raw == "INSUFFICIENT_CONTENT" or not raw:
                warnings.append("LLM declared insufficient content")
                return AutoTitleResult(
                    title=_deterministic_fallback(duration_seconds),
                    recorded_date=recorded_date,
                    method="fallback",
                    warnings=warnings,
                )
            if len(raw) > _MAX_TITLE_CHARS:
                raw = raw[: _MAX_TITLE_CHARS - 3].rstrip() + "…"
                warnings.append("LLM title exceeded 70 chars; truncated")
            return AutoTitleResult(
                title=raw,
                recorded_date=recorded_date,
                method="llm",
                warnings=warnings,
            )
        except Exception as e:  # noqa: BLE001 — any failure → fallback
            warnings.append(
                f"attempt {attempt + 1} failed: {type(e).__name__}: {e}"
            )
            if attempt >= cfg.max_retries:
                break
            time.sleep(cfg.retry_backoff_seconds * (2 ** attempt))

    return AutoTitleResult(
        title=_deterministic_fallback(duration_seconds),
        recorded_date=recorded_date,
        method="fallback",
        warnings=warnings,
    )


__all__ = [
    "AutoTitleResult",
    "generate_title",
]
