"""Format source-grounded Currents opinions for X without posting."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable

MAX_X_CHARS = 280
TCO_URL_CHARS = 23
URL_RE = re.compile(r"https://[^\s<>()]+")
CITATION_TOKEN_RE = re.compile(r"\[C:[^\]\s]+\]")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

RewriteFn = Callable[[str, int], str]


@dataclass(frozen=True)
class XFormatPayload:
    body: str
    source_url: str

    def as_dict(self) -> dict[str, str]:
        return {"body": self.body, "source_url": self.source_url}


def weighted_x_length(text: str) -> int:
    """Return X's relevant length budget, treating every URL as 23 chars."""

    total = 0
    position = 0
    for match in URL_RE.finditer(text):
        total += len(text[position : match.start()])
        total += TCO_URL_CHARS
        position = match.end()
    total += len(text[position:])
    return total


def format_for_x(
    opinion: Any,
    source_url: str,
    *,
    rewrite_fn: RewriteFn | None = None,
) -> dict[str, str] | None:
    """Return a 280-char X payload or None when it cannot be made safe.

    The function is deliberately side-effect free: callers that want an LLM
    rewrite pass inject ``rewrite_fn`` or call ``format_for_x_async``.
    """

    source_url = _clean_source_url(source_url)
    if not source_url:
        return None

    source_text = _opinion_text(opinion)
    if not source_text:
        return None

    candidate = _compose_body(source_text, source_url)
    if weighted_x_length(candidate) <= MAX_X_CHARS:
        return XFormatPayload(body=candidate, source_url=source_url).as_dict()

    if rewrite_fn is None:
        return None

    rewritten = _clean_text(rewrite_fn(source_text, _text_budget(source_url)))
    if not rewritten:
        return None
    candidate = _compose_body(rewritten, source_url)
    if weighted_x_length(candidate) <= MAX_X_CHARS:
        return XFormatPayload(body=candidate, source_url=source_url).as_dict()
    return None


async def format_for_x_async(
    opinion: Any,
    source_url: str,
    *,
    llm_client: Any | None = None,
) -> dict[str, str] | None:
    """Format a post, using one LLM rewrite pass only when needed."""

    initial = format_for_x(opinion, source_url)
    if initial is not None:
        return initial

    source_url = _clean_source_url(source_url)
    source_text = _opinion_text(opinion)
    if not source_url or not source_text:
        return None

    rewritten = await _rewrite_with_llm(
        source_text,
        _text_budget(source_url),
        llm_client=llm_client,
    )
    return format_for_x(
        opinion,
        source_url,
        rewrite_fn=lambda _text, _budget: rewritten,
    )


def _text_budget(source_url: str) -> int:
    separator_chars = 1
    return MAX_X_CHARS - TCO_URL_CHARS - separator_chars


def _compose_body(text: str, source_url: str) -> str:
    text = _clean_text(text)
    text = _strip_trailing_urls(text)
    return f"{text} {source_url}".strip()


def _opinion_text(opinion: Any) -> str:
    if isinstance(opinion, str):
        return _clean_text(opinion)
    if isinstance(opinion, dict):
        for key in ("body_markdown", "bodyMarkdown", "body", "commentary", "text"):
            if opinion.get(key):
                return _clean_text(str(opinion[key]))
        headline = str(opinion.get("headline") or "").strip()
        return _clean_text(headline)
    for key in ("body_markdown", "bodyMarkdown", "body", "commentary", "text"):
        value = getattr(opinion, key, None)
        if value:
            return _clean_text(str(value))
    return _clean_text(str(getattr(opinion, "headline", "") or ""))


def _clean_source_url(source_url: str) -> str:
    value = str(source_url or "").strip()
    if not value.startswith("https://"):
        return ""
    return value


def _clean_text(text: str) -> str:
    text = MARKDOWN_LINK_RE.sub(r"\1", text)
    text = CITATION_TOKEN_RE.sub("", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[*_>#]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -\n\t")


def _strip_trailing_urls(text: str) -> str:
    while True:
        next_text = re.sub(r"\s*https://[^\s<>()]+$", "", text).strip()
        if next_text == text:
            return text
        text = next_text


async def _rewrite_with_llm(
    text: str,
    max_non_url_chars: int,
    *,
    llm_client: Any | None,
) -> str:
    client = llm_client
    if client is None:
        from noosphere.currents._llm_client import make_client

        client = make_client()

    response = await client.complete(
        system=(
            "Rewrite the supplied Theseus Currents commentary as a single X post. "
            "Preserve the load-bearing claim and uncertainty. Return only the "
            "post body text, with no URL, no hashtags, and no fabricated source."
        ),
        user=(
            f"Max non-URL characters: {max_non_url_chars}\n\n"
            "COMMENTARY:\n"
            f"{text}"
        ),
        max_tokens=220,
        temperature=0.0,
    )
    return _clean_text(str(response.text))


def _sample_payloads() -> list[dict[str, Any]]:
    samples = [
        (
            {
                "body_markdown": (
                    "Theseus complicates the claim: the policy signal matters "
                    "less than whether institutions can preserve adversarial "
                    "review while scaling access."
                )
            },
            "https://x.com/source/status/111",
        ),
        (
            {
                "body_markdown": (
                    "The post is directionally right, but Theseus would put the "
                    "load-bearing point elsewhere: incentives reward visible "
                    "certainty before the system has earned it."
                )
            },
            "https://x.com/source/status/222",
        ),
        (
            {
                "body_markdown": (
                    "Theseus disagrees: a durable learning culture is not built "
                    "by asking people to be less wrong in public; it is built by "
                    "making revision high-status."
                )
            },
            "https://x.com/source/status/333",
        ),
    ]
    out: list[dict[str, Any]] = []
    for opinion, source_url in samples:
        payload = format_for_x(opinion, source_url)
        out.append(
            {
                "payload": payload,
                "weighted_length": weighted_x_length(payload["body"]) if payload else None,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m noosphere.social.x_formatter")
    parser.add_argument("--sample-dry-run", action="store_true")
    parser.add_argument("--format-json-stdin", action="store_true")
    args = parser.parse_args(argv)
    if args.sample_dry_run:
        print(json.dumps(_sample_payloads(), indent=2, sort_keys=True))
        return 0
    if args.format_json_stdin:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        formatted = asyncio.run(
            format_for_x_async(
                payload.get("opinion") or payload.get("text") or payload,
                str(payload.get("source_url") or payload.get("sourceUrl") or ""),
            )
        )
        print(json.dumps(formatted, sort_keys=True))
        return 0
    parser.error("no formatter action supplied")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
