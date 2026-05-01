"""Format transcript or essay artifacts into held Substack drafts."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

from noosphere.llm import LLMClient, MockLLMClient, llm_client_from_settings

SUBJECT_MAX_CHARS = 100
SUBTITLE_MAX_CHARS = 240
BLURB_MIN_WORDS = 60
BLURB_MAX_WORDS = 100
MAX_PROMPT_SOURCE_CHARS = 9000

TIMESTAMP_LINE_RE = re.compile(
    r"^\s*(?:\[|\()?((?:\d{1,2}:)?\d{1,2}:\d{2})(?:\]|\))?\s*(?:[-:]\s*)?(.*\S)?\s*$"
)


@dataclass(frozen=True)
class SubstackDraftPayload:
    subject: str
    body: str
    markdownBody: str

    def as_dict(self) -> dict[str, str]:
        return {
            "subject": self.subject,
            "body": self.body,
            "markdownBody": self.markdownBody,
        }


def format_for_substack(
    *,
    title: str,
    source_text: str,
    source_kind: str = "upload",
    llm_client: LLMClient | None = None,
) -> dict[str, str]:
    """Return a Substack draft payload from a transcript or essay.

    ``source_text`` is preserved in the final post body after only newline and
    edge whitespace normalization. The generated scaffolding is isolated above
    and below the source so founder review can clearly distinguish generated
    editorial framing from the verbatim artifact.
    """

    cleaned_source = _light_clean_source(source_text)
    subject = _subject_from_title(title, cleaned_source)
    is_session = source_kind.strip().lower() in {"session", "transcript", "dialectic"}
    timestamped_lines = _extract_timestamp_lines(cleaned_source) if is_session else []

    generated = _generated_scaffolding(
        subject=subject,
        source_text=cleaned_source,
        source_kind=source_kind,
        timestamped_lines=timestamped_lines,
        llm_client=llm_client,
    )
    subtitle = _clamp_chars(
        _single_line(generated.get("subtitle") or _fallback_subtitle(cleaned_source)),
        SUBTITLE_MAX_CHARS,
    )
    blurb = _coerce_blurb(generated.get("blurb"), cleaned_source)
    why = _coerce_why(generated.get("why_this_matters"), subject)
    highlights = _coerce_highlights(
        generated.get("highlights"),
        timestamped_lines,
    )

    source_heading = "Transcript" if is_session else "Essay"
    parts = [blurb.strip(), ""]
    if highlights:
        parts.extend(["## Highlights", ""])
        for timestamp, line in highlights:
            parts.append(f"- {timestamp} - {line}")
        parts.append("")
    parts.extend(
        [
            f"## {source_heading}",
            "",
            cleaned_source,
            "",
            "## Why this matters",
            "",
            why.strip(),
        ]
    )

    return SubstackDraftPayload(
        subject=subject,
        body=subtitle,
        markdownBody="\n".join(parts).strip() + "\n",
    ).as_dict()


def _generated_scaffolding(
    *,
    subject: str,
    source_text: str,
    source_kind: str,
    timestamped_lines: list[tuple[str, str]],
    llm_client: LLMClient | None,
) -> dict[str, Any]:
    client = llm_client if llm_client is not None else _default_llm_client()
    if client is None:
        return {}

    timestamp_context = "\n".join(
        f"{timestamp} {line}" for timestamp, line in timestamped_lines[:20]
    )
    user = {
        "title": subject,
        "source_kind": source_kind,
        "timestamped_lines": timestamp_context,
        "source_excerpt": source_text[:MAX_PROMPT_SOURCE_CHARS],
    }
    raw = client.complete(
        system=(
            "You turn Theseus founder artifacts into Substack editorial drafts. "
            "Return JSON only with keys: subtitle, blurb, highlights, "
            "why_this_matters. The blurb must be 60-100 words. Highlights must "
            "use only supplied timestamps. Do not rewrite or summarize the full "
            "source body; only write the surrounding editorial framing."
        ),
        user=json.dumps(user, ensure_ascii=False),
        max_tokens=900,
        temperature=0.2,
    )
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _default_llm_client() -> LLMClient | None:
    if os.getenv("THESEUS_SUBSTACK_FORMATTER_MOCK") == "1":
        return MockLLMClient(
            responses=[
                json.dumps(
                    {
                        "subtitle": "A concise editorial bridge from transcript to public argument.",
                        "blurb": _fallback_blurb(""),
                        "highlights": [],
                        "why_this_matters": _fallback_why("This Artifact"),
                    }
                )
            ]
        )
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")):
        return None
    try:
        return llm_client_from_settings()
    except Exception:
        return None


def _subject_from_title(title: str, source_text: str) -> str:
    candidate = _single_line(title) or _single_line(source_text.splitlines()[0] if source_text else "")
    if not candidate:
        candidate = "Untitled Theseus Session"
    return _title_case(_clamp_chars(candidate, SUBJECT_MAX_CHARS))


def _coerce_blurb(value: Any, source_text: str) -> str:
    text = _clean_generated(str(value or ""))
    words = text.split()
    if BLURB_MIN_WORDS <= len(words) <= BLURB_MAX_WORDS:
        return text
    return _fallback_blurb(source_text)


def _coerce_why(value: Any, subject: str) -> str:
    text = _clean_generated(str(value or ""))
    if len(text.split()) >= 24:
        return text
    return _fallback_why(subject)


def _coerce_highlights(
    value: Any,
    timestamped_lines: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    if not timestamped_lines:
        return []
    by_timestamp = {timestamp: line for timestamp, line in timestamped_lines}
    out: list[tuple[str, str]] = []
    if isinstance(value, list):
        for item in value:
            timestamp = ""
            line = ""
            if isinstance(item, dict):
                timestamp = str(item.get("timestamp") or "").strip()
                line = str(item.get("line") or item.get("text") or "").strip()
            elif isinstance(item, str):
                match = TIMESTAMP_LINE_RE.match(item)
                if match:
                    timestamp = match.group(1)
                    line = (match.group(2) or "").strip()
            if timestamp in by_timestamp:
                out.append((timestamp, _single_line(line or by_timestamp[timestamp])))
            if len(out) == 6:
                break
    if len(out) >= 3:
        return out
    return [(timestamp, _single_line(line)) for timestamp, line in timestamped_lines[:3]]


def _extract_timestamp_lines(source_text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in source_text.splitlines():
        match = TIMESTAMP_LINE_RE.match(line)
        if not match:
            continue
        timestamp = match.group(1)
        text = _single_line(match.group(2) or "")
        if timestamp and text:
            rows.append((timestamp, text))
    return rows


def _fallback_blurb(source_text: str) -> str:
    excerpt = _single_line(source_text)[:220]
    if excerpt:
        middle = (
            "The piece is worth reading less as a finished slogan than as a "
            "record of judgment under pressure: premises are exposed, claims "
            "are put where later evidence can reach them, and the argument is "
            "left available for revision rather than protected by vagueness."
        )
    else:
        middle = (
            "The piece is worth reading as a record of judgment under pressure: "
            "premises are exposed, claims are put where later evidence can reach "
            "them, and the argument is left available for revision rather than "
            "protected by vagueness."
        )
    text = (
        f"{excerpt}. {middle} Theseus publishes artifacts like this because "
        "private conversation compounds only when it becomes inspectable, "
        "criticizable, and durable enough to guide future decisions."
    )
    return _word_window(text, BLURB_MIN_WORDS, BLURB_MAX_WORDS)


def _fallback_subtitle(source_text: str) -> str:
    excerpt = _single_line(source_text)
    if not excerpt:
        return "A Theseus artifact prepared for founder review."
    return f"A Theseus artifact on {excerpt[:180].strip()}".strip()


def _fallback_why(subject: str) -> str:
    return (
        f"{subject} matters because the firm is trying to convert thought into "
        "intellectual capital: claims that can be inspected, attacked, priced, "
        "and revised. Publishing the record raises the standard of the argument "
        "because it makes the reasoning accountable beyond the room where it was made."
    )


def _light_clean_source(source_text: str) -> str:
    return str(source_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _clean_generated(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \n\t\"'")


def _single_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clamp_chars(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip(" ,.;:-") + "..."


def _word_window(text: str, min_words: int, max_words: int) -> str:
    words = _single_line(text).split()
    if len(words) > max_words:
        return " ".join(words[:max_words]).rstrip(" ,.;:-") + "."
    if len(words) >= min_words:
        return " ".join(words)
    seed = words[:]
    filler = (
        "That standard is the point: expose the reasoning, preserve the record, "
        "and let future evidence decide which parts deserve confidence."
    ).split()
    while len(seed) < min_words:
        seed.extend(filler)
    return " ".join(seed[:max_words]).rstrip(" ,.;:-") + "."


def _title_case(text: str) -> str:
    small = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "the", "to", "vs"}
    words = re.split(r"(\s+)", text.strip())
    result: list[str] = []
    word_index = 0
    word_total = sum(1 for part in words if part.strip())
    for part in words:
        if not part.strip():
            result.append(part)
            continue
        lower = part.lower()
        if 0 < word_index < word_total - 1 and lower in small:
            result.append(lower)
        elif part.isupper() and len(part) <= 6:
            result.append(part)
        else:
            result.append(part[:1].upper() + part[1:].lower())
        word_index += 1
    return "".join(result)


def _strip_json_fence(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _sample_payloads() -> list[dict[str, str]]:
    transcript = (
        "[00:00:12] Michael: The question is whether conviction can survive inspection.\n"
        "[00:01:44] Ada: The ledger matters because memory changes incentives.\n"
        "[00:03:02] Michael: We should publish the parts that can bear pressure."
    )
    return [
        format_for_substack(
            title="recorded reasoning as capital",
            source_text=transcript,
            source_kind="session",
        )
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m noosphere.social.substack_formatter")
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
        formatted = format_for_substack(
            title=str(payload.get("title") or ""),
            source_text=str(payload.get("source_text") or payload.get("text") or ""),
            source_kind=str(payload.get("source_kind") or payload.get("source_type") or "upload"),
        )
        print(json.dumps(formatted, sort_keys=True))
        return 0

    parser.error("no formatter action supplied")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
