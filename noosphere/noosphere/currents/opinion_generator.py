"""Haiku-backed, source-grounded Currents opinion generation."""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from noosphere.currents._llm_client import LLMResponse, make_client
from noosphere.currents.budget import BudgetExhausted
from noosphere.models import (
    CurrentEventStatus,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
)


class OpinionOutcome(str, Enum):
    PUBLISHED = "PUBLISHED"
    ABSTAINED_BUDGET = "ABSTAINED_BUDGET"
    ABSTAINED_INSUFFICIENT_SOURCES = "ABSTAINED_INSUFFICIENT_SOURCES"
    ABSTAINED_NEAR_DUPLICATE = "ABSTAINED_NEAR_DUPLICATE"
    ABSTAINED_CITATION_FABRICATION = "ABSTAINED_CITATION_FABRICATION"


OPINION_MAX_TOKENS = 1_400
MAX_JSON_FAILURES = 3
MAX_CITATION_FAILURES = 2
DEFAULT_TOP_K = 8


def retrieve_for_event(store: Any, event: Any, top_k: int = DEFAULT_TOP_K) -> list[Any]:
    """Lazy wrapper so tests that mock retrieval do not import NumPy eagerly."""
    from noosphere.currents.retrieval_adapter import retrieve_for_event as _retrieve_for_event

    return _retrieve_for_event(store, event, top_k=top_k)


def _prompt_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "_prompts" / name


def _read_system_prompt(name: str) -> str:
    return _prompt_path(name).read_text(encoding="utf-8").strip()


def _estimate_tokens(*parts: str) -> int:
    char_count = sum(len(part) for part in parts)
    return max(1, char_count // 4 + 1)


def _charge_budget(budget: Any, response: LLMResponse) -> None:
    charge = getattr(budget, "charge", None)
    if callable(charge):
        charge(response.prompt_tokens, response.completion_tokens)


def _authorize_budget(budget: Any, *, system: str, user: str, max_tokens: int) -> None:
    authorize = getattr(budget, "authorize", None)
    if callable(authorize):
        authorize(_estimate_tokens(system, user), max_tokens)


def _set_event_status(store: Any, event_id: str, status: CurrentEventStatus) -> None:
    setter = getattr(store, "set_event_status", None)
    if callable(setter):
        setter(event_id, status)


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("LLM response did not contain a JSON object") from None
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response JSON was not an object")
    return payload


def _source_blocks(hits: list[Any]) -> str:
    blocks: list[str] = []
    for idx, hit in enumerate(hits, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[SOURCE {idx}]",
                    f"source_kind: {hit.source_kind}",
                    f"source_id: {hit.source_id}",
                    f"retrieval_score: {hit.score:.6f}",
                    f"topic_hint: {hit.topic_hint or ''}",
                    f"origin: {hit.origin or ''}",
                    "text:",
                    hit.text,
                    f"[/SOURCE {idx}]",
                ]
            )
        )
    return "\n\n".join(blocks)


def _opinion_user_prompt(event: Any, hits: list[Any]) -> str:
    return "\n\n".join(
        [
            "CURRENT EVENT",
            f"event_id: {getattr(event, 'id', '')}",
            f"organization_id: {getattr(event, 'organization_id', '')}",
            f"topic_hint: {getattr(event, 'topic_hint', '') or ''}",
            "event_text:",
            getattr(event, "text", ""),
            "RETRIEVED THESEUS SOURCES",
            _source_blocks(hits),
            "Return the strict JSON object specified by the system prompt.",
        ]
    )


def _source_id_from_citation(raw: dict[str, Any], source_kind: str | None) -> str:
    source_id = raw.get("source_id") or raw.get("sourceId")
    if not source_id and source_kind == "conclusion":
        source_id = raw.get("conclusion_id") or raw.get("conclusionId")
    if not source_id and source_kind == "claim":
        source_id = raw.get("claim_id") or raw.get("claimId")
    return str(source_id or "")


def validate_citations(
    raw_citations: Any,
    hits: list[Any],
    *,
    require_any: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return normalized citations plus exact-substring validation errors."""
    if not isinstance(raw_citations, list):
        return [], ["citations must be a list"]

    by_pair = {(hit.source_kind, hit.source_id): hit for hit in hits}
    by_id: dict[str, list[Any]] = {}
    for hit in hits:
        by_id.setdefault(hit.source_id, []).append(hit)

    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    for idx, raw in enumerate(raw_citations):
        if not isinstance(raw, dict):
            errors.append(f"citation {idx} is not an object")
            continue
        raw_kind = raw.get("source_kind") or raw.get("sourceKind")
        source_kind = str(raw_kind).lower() if raw_kind else None
        if source_kind not in {"conclusion", "claim"}:
            source_kind = None
        source_id = _source_id_from_citation(raw, source_kind)
        if source_kind is None and source_id in by_id and len(by_id[source_id]) == 1:
            source_kind = by_id[source_id][0].source_kind
        quoted_span = raw.get("quoted_span") or raw.get("quotedSpan")
        if not source_kind or not source_id:
            errors.append(f"citation {idx} is missing source_kind/source_id")
            continue
        if not isinstance(quoted_span, str) or not quoted_span:
            errors.append(f"citation {idx} is missing quoted_span")
            continue
        hit = by_pair.get((source_kind, source_id))
        if hit is None:
            errors.append(f"citation {idx} cites an unretrieved source")
            continue
        if quoted_span not in hit.text:
            errors.append(f"citation {idx} quoted_span is not a verbatim substring")
            continue
        normalized.append(
            {
                "source_kind": source_kind,
                "source_id": source_id,
                "quoted_span": quoted_span,
                "retrieval_score": hit.score,
            }
        )

    if require_any and not normalized:
        errors.append("published opinions require at least one valid citation")
    return normalized, errors


def _citation_rows(citations: list[dict[str, Any]]) -> list[OpinionCitation]:
    rows: list[OpinionCitation] = []
    for citation in citations:
        source_kind = citation["source_kind"]
        source_id = citation["source_id"]
        rows.append(
            OpinionCitation(
                opinion_id="",
                source_kind=source_kind,
                conclusion_id=source_id if source_kind == "conclusion" else None,
                claim_id=source_id if source_kind == "claim" else None,
                quoted_span=citation["quoted_span"],
                retrieval_score=float(citation["retrieval_score"]),
            )
        )
    return rows


def _uncertainty_notes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


async def generate_opinion(store: Any, event_id: str, *, budget: Any) -> OpinionOutcome:
    """
    Run retrieve_for_event -> Haiku strict JSON -> verbatim citation checks ->
    write EventOpinion + OpinionCitations, or abstain with a precise outcome.
    """
    event = store.get_current_event(event_id)
    if event is None:
        raise KeyError(f"unknown current event: {event_id}")

    if getattr(event, "is_near_duplicate", False):
        _set_event_status(store, event_id, CurrentEventStatus.ABSTAINED)
        return OpinionOutcome.ABSTAINED_NEAR_DUPLICATE

    hits = retrieve_for_event(store, event, top_k=DEFAULT_TOP_K)
    if not hits:
        _set_event_status(store, event_id, CurrentEventStatus.ABSTAINED)
        return OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES

    base_system = _read_system_prompt("opinion_system.md")
    user_prompt = _opinion_user_prompt(event, hits)
    corrective = ""
    json_failures = 0
    citation_failures = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    model_name = ""
    client = None

    while json_failures < MAX_JSON_FAILURES and citation_failures < MAX_CITATION_FAILURES:
        system_prompt = base_system + corrective
        try:
            _authorize_budget(
                budget,
                system=system_prompt,
                user=user_prompt,
                max_tokens=OPINION_MAX_TOKENS,
            )
        except BudgetExhausted:
            _set_event_status(store, event_id, CurrentEventStatus.ABSTAINED)
            return OpinionOutcome.ABSTAINED_BUDGET

        if client is None:
            client = make_client()
        response = await client.complete(
            system=system_prompt,
            user=user_prompt,
            max_tokens=OPINION_MAX_TOKENS,
            temperature=0.0,
        )
        _charge_budget(budget, response)
        total_prompt_tokens += response.prompt_tokens
        total_completion_tokens += response.completion_tokens
        model_name = response.model or model_name

        try:
            payload = _extract_json_object(response.text)
        except (json.JSONDecodeError, ValueError):
            json_failures += 1
            corrective = (
                "\n\nCorrection: the previous response was not parseable strict JSON. "
                "Return only the JSON object matching the schema."
            )
            continue

        stance_raw = str(payload.get("stance", "")).upper()
        if stance_raw == OpinionStance.ABSTAINED.value:
            _set_event_status(store, event_id, CurrentEventStatus.ABSTAINED)
            return OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES
        try:
            stance = OpinionStance(stance_raw)
        except ValueError:
            json_failures += 1
            corrective = (
                "\n\nCorrection: stance must be one of AGREES, DISAGREES, "
                "COMPLICATES, or ABSTAINED."
            )
            continue

        citations, citation_errors = validate_citations(
            payload.get("citations"),
            hits,
            require_any=True,
        )
        if citation_errors:
            citation_failures += 1
            if citation_failures >= MAX_CITATION_FAILURES:
                _set_event_status(store, event_id, CurrentEventStatus.ABSTAINED)
                return OpinionOutcome.ABSTAINED_CITATION_FABRICATION
            corrective = (
                "\n\nCorrection: the previous response failed exact citation validation: "
                + "; ".join(citation_errors[:3])
                + ". Every citation quoted_span must be copied exactly from the cited source text."
            )
            continue

        opinion = EventOpinion(
            organization_id=getattr(event, "organization_id"),
            event_id=event_id,
            stance=stance,
            confidence=_confidence(payload.get("confidence")),
            headline=str(payload.get("headline") or "Theseus opinion")[:140],
            body_markdown=str(payload.get("body_markdown") or ""),
            uncertainty_notes=_uncertainty_notes(payload.get("uncertainty_notes")),
            topic_hint=payload.get("topic_hint") or getattr(event, "topic_hint", None),
            model_name=model_name or "claude-haiku-4-5",
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
        )
        try:
            store.add_event_opinion(opinion, _citation_rows(citations))
        except ValueError as exc:
            if "verbatim substring" not in str(exc):
                raise
            citation_failures += 1
            if citation_failures >= MAX_CITATION_FAILURES:
                _set_event_status(store, event_id, CurrentEventStatus.ABSTAINED)
                return OpinionOutcome.ABSTAINED_CITATION_FABRICATION
            corrective = (
                "\n\nCorrection: the previous response failed the database's "
                "verbatim citation check. Copy quoted_span exactly from source text."
            )
            continue
        _set_event_status(store, event_id, CurrentEventStatus.OPINED)
        return OpinionOutcome.PUBLISHED

    _set_event_status(store, event_id, CurrentEventStatus.ABSTAINED)
    return OpinionOutcome.ABSTAINED_CITATION_FABRICATION
