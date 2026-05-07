"""Haiku-backed, source-grounded Currents opinion generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from noosphere.currents._llm_client import LLMResponse, make_client
from noosphere.currents.budget import BudgetExhausted
from noosphere.models import (
    AbstentionReason,
    CurrentEventStatus,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
)


class OpinionOutcome(str, Enum):
    PUBLISHED = "PUBLISHED"
    ABSTAINED_OFF_DOMAIN = "ABSTAIN_OFF_DOMAIN"
    ABSTAINED_BUDGET = "ABSTAINED_BUDGET"
    ABSTAINED_INSUFFICIENT_SOURCES = "ABSTAINED_INSUFFICIENT_SOURCES"
    ABSTAINED_NEAR_DUPLICATE = "ABSTAINED_NEAR_DUPLICATE"
    ABSTAINED_CITATION_FABRICATION = "ABSTAINED_CITATION_FABRICATION"


OPINION_MAX_TOKENS = 1_400
MAX_JSON_FAILURES = 3
MAX_CITATION_FAILURES = 2
DEFAULT_TOP_K = 12
MIN_CONCLUSIONS_FOR_OPINION = 3
MIN_CORPUS_SOURCES_FOR_OPINION = 3
MIN_CONCLUSION_SCORE = 0.55
EVENT_METRIC_FIELDS = (
    "significance_score",
    "retweet_count",
    "like_count",
    "reply_count",
    "quote_count",
    "bookmark_count",
    "impression_count",
)
CONCLUSION_TOKEN_RE = re.compile(r"\[C:([^\]\s]+)\]")
GENERIC_EVENT_SUBJECT_RE = re.compile(
    (
        r"\b(?:(?:the|this|that|observed|source|current)\s+event|event's|"
        r"in\s+the\s+event)\b"
    ),
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class OpinionDryRun:
    event_id: str
    eligible: bool
    reason: str | None
    retrieved_conclusions: int
    prompt_conclusion_citations: int
    system_prompt_chars: int
    user_prompt_chars: int


def retrieve_for_event(store: Any, event: Any, top_k: int = DEFAULT_TOP_K) -> list[Any]:
    """Lazy wrapper so tests that mock retrieval do not import NumPy eagerly."""
    from noosphere.currents.retrieval_adapter import (
        retrieve_for_event as _retrieve_for_event,
    )

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
    from noosphere.currents.retrieval_adapter import corpus_source_key

    blocks: list[str] = []
    for idx, hit in enumerate(hits, start=1):
        label = "FIRM CONCLUSION" if hit.source_kind == "conclusion" else "SOURCE"
        source_upload_ids = tuple(getattr(hit, "source_upload_ids", ()) or ())
        citation_token = (
            [f"citation_token: [C:{hit.source_id}]"]
            if hit.source_kind == "conclusion"
            else []
        )
        blocks.append(
            "\n".join(
                [
                    f"[{label} {idx}]",
                    *citation_token,
                    f"source_kind: {hit.source_kind}",
                    f"source_id: {hit.source_id}",
                    f"corpus_source_key: {corpus_source_key(hit)}",
                    f"corpus_upload_ids: {json.dumps(list(source_upload_ids))}",
                    f"retrieval_score: {hit.score:.6f}",
                    f"topic_hint: {hit.topic_hint or ''}",
                    f"origin: {hit.origin or ''}",
                    "text:",
                    hit.text,
                    f"[/{label} {idx}]",
                ]
            )
        )
    return "\n\n".join(blocks)


def _event_metrics(event: Any) -> dict[str, float | int]:
    raw = getattr(event, "metrics", None)
    if raw is None:
        return {}
    if hasattr(raw, "model_dump"):
        data = raw.model_dump(mode="json")
    elif isinstance(raw, dict):
        data = raw
    else:
        data = {
            field: getattr(raw, field)
            for field in EVENT_METRIC_FIELDS
            if hasattr(raw, field)
        }

    metrics: dict[str, float | int] = {}
    for field in EVENT_METRIC_FIELDS:
        value = data.get(field) if isinstance(data, dict) else None
        if isinstance(value, bool) or value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if field == "significance_score":
            metrics[field] = round(number, 6)
        else:
            metrics[field] = int(number)
    return metrics


def _event_metrics_block(event: Any) -> str:
    metrics = _event_metrics(event)
    if not metrics:
        return "event_metrics: unavailable"
    return "\n".join(
        ["event_metrics:"]
        + [
            f"{field}: {metrics[field]}"
            for field in EVENT_METRIC_FIELDS
            if field in metrics
        ]
    )


def _primary_event_metric(
    metrics: dict[str, float | int],
) -> tuple[str, float | int | None]:
    significance = metrics.get("significance_score")
    if isinstance(significance, int | float) and significance > 0:
        return "significance_score", significance
    count_fields = [
        field for field in EVENT_METRIC_FIELDS if field != "significance_score"
    ]
    present = [(field, metrics[field]) for field in count_fields if field in metrics]
    if not present:
        return "unavailable", None
    return max(present, key=lambda item: float(item[1]))


def _citation_justification_metadata(event: Any) -> dict[str, Any]:
    metrics = _event_metrics(event)
    primary_metric, primary_value = _primary_event_metric(metrics)
    return {
        "event_id": str(getattr(event, "id", "") or ""),
        "event_source": _event_source_value(event),
        "primary_event_metric": primary_metric,
        "primary_event_metric_value": primary_value,
        "event_metrics": metrics,
    }


def _event_source_value(event: Any) -> str:
    source = getattr(event, "source", "")
    return str(getattr(source, "value", source) or "")


def _event_source_label(event: Any) -> str:
    normalized = _event_source_value(event).strip().upper()
    if normalized in {"X", "X_TWITTER", "TWITTER"}:
        return "X POST"
    if normalized == "RSS":
        return "RSS ITEM"
    return "SOURCE ITEM"


def _event_text_label(event: Any) -> str:
    return "post_text:" if _event_source_label(event) == "X POST" else "source_text:"


def _event_subject_guidance(event: Any) -> str:
    if _event_source_label(event) == "X POST":
        return (
            "Refer to this source as the post, the X post, the author, or the "
            "claim. Do not use 'the event', 'this event', 'that event', or "
            "'the current event' as the subject of the opinion."
        )
    return (
        "Refer to this source item concretely by its author, source, title, "
        "claim, or text when the analysis needs a subject."
    )


def _opinion_user_prompt(event: Any, hits: list[Any]) -> str:
    source_label = _event_source_label(event)
    return "\n\n".join(
        [
            f"TRENDING EVENT SUBJECT ({source_label})",
            f"observed_item: OBSERVED {source_label}",
            f"event_id: {getattr(event, 'id', '')}",
            f"organization_id: {getattr(event, 'organization_id', '')}",
            f"source: {_event_source_value(event)}",
            f"external_id: {getattr(event, 'external_id', '')}",
            f"author_handle: {getattr(event, 'author_handle', '') or ''}",
            f"source_url: {getattr(event, 'url', '') or ''}",
            f"observed_at: {getattr(event, 'observed_at', '') or ''}",
            f"captured_at: {getattr(event, 'captured_at', '') or ''}",
            f"topic_hint: {getattr(event, 'topic_hint', '') or ''}",
            _event_metrics_block(event),
            _event_text_label(event),
            getattr(event, "text", ""),
            "FIRM PRIOR CONCLUSIONS AS COMMENTARY VOICE",
            (
                "The excerpts below are what this firm has previously argued "
                "that may be relevant to the event. Comment on the event using "
                "the firm's prior conclusions; do not pretend the conclusions "
                "caused the event."
            ),
            _source_blocks(hits),
            "ANALYSIS TASK",
            (
                "Write the firm's response to this specific observed "
                f"{source_label.lower()}. The event is the subject; the firm's "
                "prior conclusions are the commentator's voice. Do not refer to "
                "an undefined event; name the post, its author, or its claim when "
                "the analysis needs a subject."
            ),
            _event_subject_guidance(event),
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


def _citation_rows(
    citations: list[dict[str, Any]],
    *,
    event: Any,
) -> list[OpinionCitation]:
    rows: list[OpinionCitation] = []
    justification_metadata = _citation_justification_metadata(event)
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
                justification_metadata=dict(justification_metadata),
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


def _eligible_conclusion_hits(hits: list[Any]) -> list[Any]:
    return [
        hit
        for hit in hits[:DEFAULT_TOP_K]
        if hit.source_kind == "conclusion" and hit.score >= MIN_CONCLUSION_SCORE
    ]


def _distinct_corpus_source_count(hits: list[Any]) -> int:
    from noosphere.currents.retrieval_adapter import distinct_corpus_source_count

    return distinct_corpus_source_count(hits)


def _insufficient_context_reason(hits: list[Any]) -> str | None:
    if len(hits) < MIN_CONCLUSIONS_FOR_OPINION:
        return "fewer_than_3_relevant_conclusions"
    if _distinct_corpus_source_count(hits) < MIN_CORPUS_SOURCES_FOR_OPINION:
        return "fewer_than_3_distinct_corpus_sources"
    return None


def _off_domain_hits(retrieved_hits: list[Any], eligible_hits: list[Any]) -> bool:
    return bool(retrieved_hits) and not eligible_hits


def _write_abstention_opinion(
    store: Any,
    event: Any,
    *,
    reason: AbstentionReason,
) -> None:
    opinion = EventOpinion(
        organization_id=getattr(event, "organization_id"),
        event_id=str(getattr(event, "id")),
        stance=OpinionStance.ABSTAINED,
        confidence=0.0,
        headline="No firm opinion",
        body_markdown="",
        uncertainty_notes=[],
        topic_hint=getattr(event, "topic_hint", None),
        model_name="retrieval-gate",
        prompt_tokens=0,
        completion_tokens=0,
        abstention_reason=reason,
    )
    store.add_event_opinion(opinion, [])


def _opinion_dry_run(
    event: Any,
    hits: list[Any],
    *,
    retrieved_hits: list[Any],
) -> OpinionDryRun:
    base_system = _read_system_prompt("opinion_system.md")
    user_prompt = _opinion_user_prompt(event, hits)
    inline_ids = set(CONCLUSION_TOKEN_RE.findall(user_prompt))
    reason = (
        OpinionOutcome.ABSTAINED_OFF_DOMAIN.value
        if _off_domain_hits(retrieved_hits, hits)
        else _insufficient_context_reason(hits)
    )
    return OpinionDryRun(
        event_id=str(getattr(event, "id", "")),
        eligible=reason is None,
        reason=reason,
        retrieved_conclusions=len(hits),
        prompt_conclusion_citations=len(inline_ids),
        system_prompt_chars=len(base_system),
        user_prompt_chars=len(user_prompt),
    )


def _inline_conclusion_errors(
    body_markdown: str,
    citations: list[dict[str, Any]],
) -> list[str]:
    conclusion_ids = {
        citation["source_id"]
        for citation in citations
        if citation["source_kind"] == "conclusion"
    }
    errors: list[str] = []
    if len(conclusion_ids) < MIN_CONCLUSIONS_FOR_OPINION:
        errors.append(
            "published opinions require at least 3 valid Conclusion citations"
        )

    inline_ids = set(CONCLUSION_TOKEN_RE.findall(body_markdown))
    supported_inline_ids = inline_ids.intersection(conclusion_ids)
    if len(supported_inline_ids) < MIN_CONCLUSIONS_FOR_OPINION:
        errors.append(
            "body_markdown must cite at least 3 firm Conclusions inline with "
            "[C:<id>] tokens"
        )
    return errors


def _source_subject_errors(event: Any, headline: str, body_markdown: str) -> list[str]:
    if _event_source_label(event) != "X POST":
        return []
    haystack = "\n".join([headline, body_markdown])
    if GENERIC_EVENT_SUBJECT_RE.search(haystack):
        return [
            "X-post opinions must refer to the observed source as a post, "
            "X post, author, or claim, not as a generic event"
        ]
    return []


async def generate_opinion(
    store: Any,
    event_id: str,
    *,
    budget: Any,
    dry_run: bool = False,
) -> OpinionOutcome | OpinionDryRun:
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

    retrieved_hits = retrieve_for_event(store, event, top_k=DEFAULT_TOP_K)
    hits = _eligible_conclusion_hits(retrieved_hits)
    if dry_run:
        return _opinion_dry_run(event, hits, retrieved_hits=retrieved_hits)

    if _off_domain_hits(retrieved_hits, hits):
        _write_abstention_opinion(
            store,
            event,
            reason=AbstentionReason.ABSTAIN_OFF_DOMAIN,
        )
        _set_event_status(store, event_id, CurrentEventStatus.ABSTAINED)
        return OpinionOutcome.ABSTAINED_OFF_DOMAIN

    if _insufficient_context_reason(hits) is not None:
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

    while (
        json_failures < MAX_JSON_FAILURES and citation_failures < MAX_CITATION_FAILURES
    ):
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

        raw_text = response.text.strip()
        if raw_text == "":
            _set_event_status(store, event_id, CurrentEventStatus.ABSTAINED)
            return OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES

        try:
            payload = _extract_json_object(raw_text)
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

        headline = str(payload.get("headline") or "Theseus opinion")[:140]
        body_markdown = str(payload.get("body_markdown") or "")
        subject_errors = _source_subject_errors(event, headline, body_markdown)
        if subject_errors:
            json_failures += 1
            corrective = (
                "\n\nCorrection: the previous response described the observed "
                "source too abstractly: "
                + "; ".join(subject_errors)
                + ". Rewrite the headline and body so the X post, its author, "
                "or its claim is the object being analyzed."
            )
            continue

        citations, citation_errors = validate_citations(
            payload.get("citations"),
            hits,
            require_any=True,
        )
        citation_errors.extend(
            _inline_conclusion_errors(
                str(payload.get("body_markdown") or ""),
                citations,
            )
        )
        if citation_errors:
            citation_failures += 1
            if citation_failures >= MAX_CITATION_FAILURES:
                _set_event_status(store, event_id, CurrentEventStatus.ABSTAINED)
                return OpinionOutcome.ABSTAINED_CITATION_FABRICATION
            corrective = (
                "\n\nCorrection: the previous response failed exact citation "
                "validation: "
                + "; ".join(citation_errors[:3])
                + ". Every citation quoted_span must be copied exactly from the "
                "cited source text."
            )
            continue

        opinion = EventOpinion(
            organization_id=getattr(event, "organization_id"),
            event_id=event_id,
            stance=stance,
            confidence=_confidence(payload.get("confidence")),
            headline=headline,
            body_markdown=body_markdown,
            uncertainty_notes=_uncertainty_notes(payload.get("uncertainty_notes")),
            topic_hint=payload.get("topic_hint") or getattr(event, "topic_hint", None),
            model_name=model_name or "claude-haiku-4-5",
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
        )
        try:
            store.add_event_opinion(opinion, _citation_rows(citations, event=event))
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
