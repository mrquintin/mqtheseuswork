"""Haiku-backed, principle-grounded equity signal generation.

Signal flow mirrors :mod:`noosphere.forecasts.forecast_generator`:
retrieval → strict-JSON LLM → verbatim-citation validator → budget
guard → persist. The only structural difference is that an equity
signal is grounded in PRINCIPLES, not in markets — the generator
refuses to publish a signal that cites only raw claims.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from noosphere.currents._llm_client import LLMResponse, make_client
from noosphere.currents.budget import BudgetExhausted
from noosphere.currents.opinion_generator import (
    _estimate_tokens,
    _extract_json_object,
)
from noosphere.mitigations.prompt_separator import PromptSeparator
from noosphere.models import (
    EquitySignal,
    EquitySignalCitation,
    EquitySignalDirection,
    EquitySignalStatus,
    ForecastSupportLabel,
)


class SignalOutcome(str, Enum):
    PUBLISHED = "PUBLISHED"
    ABSTAINED_INSUFFICIENT_PRINCIPLES = "ABSTAINED_INSUFFICIENT_PRINCIPLES"
    ABSTAINED_NO_DOMAIN_MATCH = "ABSTAINED_NO_DOMAIN_MATCH"
    ABSTAINED_NEAR_DUPLICATE = "ABSTAINED_NEAR_DUPLICATE"
    ABSTAINED_BUDGET = "ABSTAINED_BUDGET"
    ABSTAINED_CITATION_FABRICATION = "ABSTAINED_CITATION_FABRICATION"
    ABSTAINED_RECENTLY_REVISED = "ABSTAINED_RECENTLY_REVISED"


SIGNAL_MAX_TOKENS = 1_800
MAX_JSON_FAILURES = 3
MAX_SCHEMA_FAILURES = 2
MAX_CITATION_FAILURES = 2
DEFAULT_TOP_K = 10
MIN_PRINCIPLE_SOURCES = 2
NEAR_DUPLICATE_COSINE = 0.92
NEAR_DUPLICATE_WINDOW = timedelta(hours=24)
ORG_ID_DEFAULT = "org_equities"
PROMPT_SEPARATOR_BEGIN = "<<<PROMPT_SEPARATOR_EQUITY_BUNDLE_BEGIN>>>"
PROMPT_SEPARATOR_END = "<<<PROMPT_SEPARATOR_EQUITY_BUNDLE_END>>>"

SIGNAL_SCHEMA_KEYS = {
    "direction",
    "confidence_low",
    "confidence_high",
    "target_price_low",
    "target_price_high",
    "horizon_days",
    "headline",
    "reasoning_markdown",
    "uncertainty_notes",
    "citations",
}
CITATION_KEYS = {"source_type", "source_id", "quoted_span", "support_label"}
DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL"}
SOURCE_TYPES = {"PRINCIPLE", "CONCLUSION", "CLAIM"}
SUPPORT_LABELS = {"DIRECT", "INDIRECT", "CONTRARY"}
HORIZON_MIN_DAYS = 7
HORIZON_MAX_DAYS = 365

# Technical-analysis vocabulary the generator must never emit. We use this as
# a defensive screen on the final reasoning_markdown — the system prompt also
# forbids these, but a screen here makes the contract enforceable in code.
TECHNICAL_TERMS = (
    "moving average",
    "rsi",
    "macd",
    "candlestick",
    "head and shoulders",
    "fibonacci",
    "support level",
    "resistance level",
    "bollinger",
    "stochastic oscillator",
    "ichimoku",
    "death cross",
    "golden cross",
)


@dataclass(frozen=True)
class _CitationValidationHit:
    source_kind: str
    source_id: str
    text: str
    score: float


def retrieve_for_instrument(store: Any, instrument: Any, top_k: int = DEFAULT_TOP_K) -> list[Any]:
    """Lazy wrapper so tests that monkeypatch retrieval don't import NumPy eagerly."""
    from noosphere.equities.retrieval_adapter import (
        retrieve_for_instrument as _retrieve,
    )

    return _retrieve(store, instrument, top_k=top_k)


def embed_text(text: str) -> Any:
    """Embed text using the same local embedding seam as Currents."""
    from noosphere.currents.enrich import embed_text as _embed_text

    return _embed_text(text)


def _prompt_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "_prompts" / name


def _read_system_prompt(name: str) -> str:
    return _prompt_path(name).read_text(encoding="utf-8").strip()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _status_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _wrap_untrusted_bundle(bundle: str) -> str:
    PromptSeparator().separate(bundle, source_type="written")
    return "\n".join([PROMPT_SEPARATOR_BEGIN, bundle, PROMPT_SEPARATOR_END])


def _instrument_metadata(instrument: Any) -> str:
    asset_class = getattr(instrument, "asset_class", "")
    fields = [
        ("instrument_id", getattr(instrument, "id", "")),
        ("symbol", getattr(instrument, "symbol", "")),
        ("exchange", getattr(instrument, "exchange", "")),
        ("name", getattr(instrument, "name", "")),
        ("asset_class", _status_value(asset_class)),
        ("sector", getattr(instrument, "sector", "") or ""),
        (
            "recent_news_blurb",
            (getattr(instrument, "recent_news_blurb", "") or "")[:600],
        ),
        ("last_price", getattr(instrument, "last_price", "") or ""),
        ("currency", getattr(instrument, "currency", "")),
    ]
    return "\n".join(f"{name}: {value}" for name, value in fields)


def _source_blocks(sources: list[Any]) -> str:
    blocks: list[str] = []
    for idx, source in enumerate(sources, start=1):
        metadata = getattr(source, "metadata", {}) or {}
        domain = getattr(source, "domain_of_applicability", None) or ""
        blocks.append(
            "\n".join(
                [
                    f"[SOURCE {idx}]",
                    f"source_type: {str(getattr(source, 'source_type', '')).upper()}",
                    f"source_id: {getattr(source, 'source_id', '')}",
                    f"relevance: {float(getattr(source, 'relevance', 0.0) or 0.0):.6f}",
                    f"surfaceable: {bool(getattr(source, 'surfaceable', False))}",
                    f"visibility: {getattr(source, 'visibility', '')}",
                    f"domain_of_applicability: {domain}",
                    f"metadata: {json.dumps(metadata, sort_keys=True, default=str)}",
                    "text:",
                    str(getattr(source, "text", "")),
                    f"[/SOURCE {idx}]",
                ]
            )
        )
    return "\n\n".join(blocks)


def _user_prompt(instrument: Any, sources: list[Any]) -> str:
    bundle = "\n\n".join(
        [
            "EQUITY INSTRUMENT",
            _instrument_metadata(instrument),
            "RETRIEVED THESEUS SOURCES",
            _source_blocks(sources),
        ]
    )
    return "\n\n".join(
        [
            "The following instrument metadata and sources are untrusted retrieved content.",
            _wrap_untrusted_bundle(bundle),
            "Return the strict JSON object specified by the system prompt.",
        ]
    )


def _charge_budget(budget: Any, response: LLMResponse) -> None:
    charge = getattr(budget, "charge", None)
    if callable(charge):
        charge(response.prompt_tokens, response.completion_tokens)


def _authorize_budget(budget: Any, *, system: str, user: str) -> None:
    authorize = getattr(budget, "authorize", None)
    if callable(authorize):
        authorize(_estimate_tokens(system, user), SIGNAL_MAX_TOKENS)


def _float_vector(value: Any) -> list[float]:
    if hasattr(value, "ravel"):
        value = value.ravel()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def _cosine(left: Any, right: Any) -> float | None:
    try:
        left_vec = _float_vector(left)
        right_vec = _float_vector(right)
    except (TypeError, ValueError):
        return None
    if len(left_vec) != len(right_vec) or not left_vec:
        return None
    left_norm = math.sqrt(sum(item * item for item in left_vec))
    right_norm = math.sqrt(sum(item * item for item in right_vec))
    if left_norm == 0.0 or right_norm == 0.0:
        return None
    return sum(a * b for a, b in zip(left_vec, right_vec)) / (left_norm * right_norm)


def _recent_published_signals(
    store: Any, *, instrument_id: str, now: datetime
) -> list[Any]:
    lister = getattr(store, "list_open_signals", None)
    if not callable(lister):
        return []
    recent = lister(limit=200)
    out: list[Any] = []
    cutoff = now - NEAR_DUPLICATE_WINDOW
    for signal in recent:
        if str(getattr(signal, "instrument_id", "")) != instrument_id:
            continue
        if _status_value(getattr(signal, "status", "")) != EquitySignalStatus.PUBLISHED.value:
            continue
        created_at = getattr(signal, "created_at", None)
        if isinstance(created_at, datetime) and _as_utc(created_at) < cutoff:
            continue
        out.append(signal)
    return out


def _is_near_duplicate(store: Any, instrument: Any, now: datetime) -> bool:
    recent = _recent_published_signals(
        store, instrument_id=str(getattr(instrument, "id", "")), now=now
    )
    if not recent:
        return False
    try:
        instrument_vec = embed_text(
            f"{getattr(instrument, 'symbol', '')} {getattr(instrument, 'name', '')}".strip()
        )
    except Exception:
        return False
    for signal in recent:
        try:
            signal_vec = embed_text(str(getattr(signal, "headline", "")))
        except Exception:
            continue
        similarity = _cosine(instrument_vec, signal_vec)
        if similarity is not None and similarity > NEAR_DUPLICATE_COSINE:
            return True
    return False


def _as_float(value: Any, field: str, errors: list[str]) -> float | None:
    if isinstance(value, bool):
        errors.append(f"{field} must be a number")
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be a number")
        return None
    if not 0.0 <= parsed <= 1.0:
        errors.append(f"{field} must be between 0.0 and 1.0")
        return None
    return parsed


def _optional_price(value: Any, field: str, errors: list[str]) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be a number or null")
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be a number or null")
        return None
    if parsed < 0.0:
        errors.append(f"{field} must be non-negative")
        return None
    return parsed


def _text_field(payload: dict[str, Any], field: str, limit: int, errors: list[str]) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        errors.append(f"{field} must be a string")
        return ""
    if len(value) > limit:
        errors.append(f"{field} must be <= {limit} chars")
    return value.strip()


def _schema_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(SIGNAL_SCHEMA_KEYS - set(payload))
    extra = sorted(set(payload) - SIGNAL_SCHEMA_KEYS)
    if missing:
        errors.append("missing required keys: " + ", ".join(missing))
    if extra:
        errors.append("unexpected keys: " + ", ".join(extra))

    direction = payload.get("direction")
    if direction not in DIRECTIONS:
        errors.append("direction must be BULLISH, BEARISH, or NEUTRAL")

    low = _as_float(payload.get("confidence_low"), "confidence_low", errors)
    high = _as_float(payload.get("confidence_high"), "confidence_high", errors)
    if low is not None and high is not None and high < low:
        errors.append("confidence_high must be >= confidence_low")

    target_low = _optional_price(
        payload.get("target_price_low"), "target_price_low", errors
    )
    target_high = _optional_price(
        payload.get("target_price_high"), "target_price_high", errors
    )
    if (
        target_low is not None
        and target_high is not None
        and target_high < target_low
    ):
        errors.append("target_price_high must be >= target_price_low")

    horizon = payload.get("horizon_days")
    if isinstance(horizon, bool) or not isinstance(horizon, int):
        errors.append("horizon_days must be an integer")
    elif not HORIZON_MIN_DAYS <= horizon <= HORIZON_MAX_DAYS:
        errors.append(
            f"horizon_days must be between {HORIZON_MIN_DAYS} and {HORIZON_MAX_DAYS}"
        )

    _text_field(payload, "headline", 140, errors)
    reasoning = _text_field(payload, "reasoning_markdown", 1800, errors)
    _text_field(payload, "uncertainty_notes", 500, errors)

    if reasoning:
        lowered = reasoning.lower()
        for term in TECHNICAL_TERMS:
            if term in lowered:
                errors.append(
                    f"reasoning_markdown references a technical-analysis term ({term})"
                )
                break

    citations = payload.get("citations")
    if not isinstance(citations, list):
        errors.append("citations must be a list")
        return errors
    for idx, citation in enumerate(citations):
        if not isinstance(citation, dict):
            errors.append(f"citation {idx} must be an object")
            continue
        missing_citation = sorted(CITATION_KEYS - set(citation))
        extra_citation = sorted(set(citation) - CITATION_KEYS)
        if missing_citation:
            errors.append(
                f"citation {idx} missing required keys: " + ", ".join(missing_citation)
            )
        if extra_citation:
            errors.append(
                f"citation {idx} unexpected keys: " + ", ".join(extra_citation)
            )
        if citation.get("source_type") not in SOURCE_TYPES:
            errors.append(f"citation {idx} source_type must be one of {sorted(SOURCE_TYPES)}")
        if not isinstance(citation.get("source_id"), str) or not citation.get("source_id"):
            errors.append(f"citation {idx} source_id must be a non-empty string")
        quoted_span = citation.get("quoted_span")
        if not isinstance(quoted_span, str) or not quoted_span:
            errors.append(f"citation {idx} quoted_span must be a non-empty string")
        elif len(quoted_span) > 240:
            errors.append(f"citation {idx} quoted_span must be <= 240 chars")
        if citation.get("support_label") not in SUPPORT_LABELS:
            errors.append(f"citation {idx} support_label is invalid")
    return errors


def _validation_hits(sources: list[Any]) -> list[_CitationValidationHit]:
    return [
        _CitationValidationHit(
            source_kind=str(getattr(source, "source_type", "")).lower(),
            source_id=str(getattr(source, "source_id", "")),
            text=str(getattr(source, "text", "")),
            score=float(getattr(source, "relevance", 0.0) or 0.0),
        )
        for source in sources
    ]


def _validate_signal_citations(
    payload: dict[str, Any], sources: list[Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Verbatim-substring check against PRINCIPLE/CONCLUSION/CLAIM hits.

    The Currents validator only knows about ``conclusion``/``claim`` source
    kinds, so we replicate its exact-substring contract here ourselves and
    key it off the equity adapter's ``PRINCIPLE``/``CONCLUSION``/``CLAIM``
    taxonomy.
    """

    raw_citations = payload.get("citations")
    if not isinstance(raw_citations, list):
        return [], ["citations must be a list"]

    by_pair: dict[tuple[str, str], _CitationValidationHit] = {}
    for hit in _validation_hits(sources):
        by_pair[(hit.source_kind.upper(), hit.source_id)] = hit

    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    for idx, raw in enumerate(raw_citations):
        if not isinstance(raw, dict):
            errors.append(f"citation {idx} is not an object")
            continue
        source_type = str(raw.get("source_type", "")).upper()
        source_id = str(raw.get("source_id", ""))
        quoted_span = raw.get("quoted_span")
        if source_type not in SOURCE_TYPES or not source_id:
            errors.append(f"citation {idx} is missing source_type/source_id")
            continue
        if not isinstance(quoted_span, str) or not quoted_span:
            errors.append(f"citation {idx} is missing quoted_span")
            continue
        hit = by_pair.get((source_type, source_id))
        if hit is None:
            errors.append(f"citation {idx} cites an unretrieved source")
            continue
        if quoted_span not in hit.text:
            errors.append(f"citation {idx} quoted_span is not a verbatim substring")
            continue
        normalized.append(
            {
                "source_kind": source_type.lower(),
                "source_id": source_id,
                "quoted_span": quoted_span,
                "retrieval_score": hit.score,
            }
        )
    if not normalized:
        errors.append("published signals require at least one valid citation")
    if errors:
        return [], errors
    return _attach_support_labels(payload, normalized)


def _attach_support_labels(
    payload: dict[str, Any], normalized: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    raw_citations = payload.get("citations") or []
    by_key = {
        (
            str(raw.get("source_type", "")).upper(),
            str(raw.get("source_id", "")),
            str(raw.get("quoted_span", "")),
        ): str(raw.get("support_label", ""))
        for raw in raw_citations
        if isinstance(raw, dict)
    }
    out: list[dict[str, Any]] = []
    errors: list[str] = []
    for citation in normalized:
        source_type = str(citation["source_kind"]).upper()
        key = (source_type, citation["source_id"], citation["quoted_span"])
        support_label = by_key.get(key, "")
        if support_label not in SUPPORT_LABELS:
            errors.append("validated citation is missing a valid support_label")
            continue
        out.append(
            {
                "source_type": source_type,
                "source_id": citation["source_id"],
                "quoted_span": citation["quoted_span"],
                "support_label": support_label,
                "retrieval_score": citation["retrieval_score"],
            }
        )
    if errors:
        return [], errors
    return out, []


def _principle_citation_count(citations: list[dict[str, Any]]) -> int:
    return sum(
        1 for c in citations if str(c.get("source_type", "")).upper() == "PRINCIPLE"
    )


def _signal_direction(payload: dict[str, Any]) -> EquitySignalDirection:
    return EquitySignalDirection(str(payload["direction"]))


def _decimal_confidence(value: Any) -> Decimal:
    return Decimal(str(round(float(value), 6))).quantize(Decimal("0.000001"))


def _decimal_price(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(round(float(value), 6))).quantize(Decimal("0.000001"))


def _principle_count(sources: list[Any]) -> int:
    return sum(
        1
        for source in sources
        if str(getattr(source, "source_type", "")).upper() == "PRINCIPLE"
    )


async def generate_signal(
    store: Any,
    instrument_id: str,
    *,
    budget: Any,
    organization_id: str | None = None,
) -> SignalOutcome:
    """Generate one EquitySignal for ``instrument_id`` or abstain with a precise outcome.

    Parameters
    ----------
    store:
        The Noosphere store; must expose ``get_equity_instrument``,
        ``put_equity_signal``, ``put_equity_signal_citation`` and (for the
        near-duplicate gate) ``list_open_signals``.
    instrument_id:
        Primary key of the :class:`~noosphere.models.EquityInstrument` to
        assess.
    budget:
        Hourly budget guard; must expose ``authorize`` and ``charge``.
    organization_id:
        Tenant id stamped on the resulting row. Falls back to ``ORG_ID_DEFAULT``.
    """

    instrument = store.get_equity_instrument(instrument_id)
    if instrument is None:
        raise KeyError(f"unknown equity instrument: {instrument_id}")

    now = _utcnow()
    sources = retrieve_for_instrument(store, instrument, top_k=DEFAULT_TOP_K)
    if not sources:
        return SignalOutcome.ABSTAINED_NO_DOMAIN_MATCH
    if _principle_count(sources) < MIN_PRINCIPLE_SOURCES:
        return SignalOutcome.ABSTAINED_INSUFFICIENT_PRINCIPLES

    if _is_near_duplicate(store, instrument, now):
        return SignalOutcome.ABSTAINED_NEAR_DUPLICATE

    base_system = _read_system_prompt("signal_system.md")
    user_prompt = _user_prompt(instrument, sources)
    corrective = ""
    json_failures = 0
    schema_failures = 0
    citation_failures = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    model_name = ""
    client = None

    while True:
        system_prompt = base_system + corrective
        try:
            _authorize_budget(budget, system=system_prompt, user=user_prompt)
        except BudgetExhausted:
            return SignalOutcome.ABSTAINED_BUDGET

        if client is None:
            client = make_client()
        response = await client.complete(
            system=system_prompt,
            user=user_prompt,
            max_tokens=SIGNAL_MAX_TOKENS,
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
            if json_failures >= MAX_JSON_FAILURES:
                return SignalOutcome.ABSTAINED_CITATION_FABRICATION
            corrective = (
                "\n\nCorrection: the previous response was not parseable strict JSON. "
                "Return only the JSON object matching the equity signal schema."
            )
            continue

        schema_errors = _schema_errors(payload)
        if schema_errors:
            schema_failures += 1
            if schema_failures >= MAX_SCHEMA_FAILURES:
                return SignalOutcome.ABSTAINED_CITATION_FABRICATION
            corrective = (
                "\n\nCorrection: the previous response failed schema validation: "
                + "; ".join(schema_errors[:4])
                + ". Direction must be BULLISH/BEARISH/NEUTRAL, confidence_high "
                ">= confidence_low, horizon_days in [7, 365], no technical "
                "analysis terms."
            )
            continue

        citations, citation_errors = _validate_signal_citations(payload, sources)
        if citation_errors:
            citation_failures += 1
            if citation_failures >= MAX_CITATION_FAILURES:
                return SignalOutcome.ABSTAINED_CITATION_FABRICATION
            corrective = (
                "\n\nCorrection: the previous response failed exact citation validation: "
                + "; ".join(citation_errors[:4])
                + ". Every citation quoted_span must be copied exactly from the cited source text."
            )
            continue

        if _principle_citation_count(citations) < 1:
            # Code-level refusal: a directional signal MUST cite at least one
            # principle. Citing only raw claims is not the firm's posture.
            return SignalOutcome.ABSTAINED_INSUFFICIENT_PRINCIPLES

        org_id = organization_id or (
            getattr(instrument, "organization_id", "") or ORG_ID_DEFAULT
        )
        signal = EquitySignal(
            instrument_id=instrument_id,
            organization_id=org_id,
            direction=_signal_direction(payload),
            confidence_low=_decimal_confidence(payload["confidence_low"]),
            confidence_high=_decimal_confidence(payload["confidence_high"]),
            target_price_low=_decimal_price(payload.get("target_price_low")),
            target_price_high=_decimal_price(payload.get("target_price_high")),
            horizon_days=int(payload["horizon_days"]),
            headline=str(payload["headline"]).strip()[:140],
            reasoning=str(payload["reasoning_markdown"]).strip(),
            model_name=model_name or "claude-haiku-4-5",
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            status=EquitySignalStatus.PUBLISHED,
        )
        signal_id = store.put_equity_signal(signal)
        for citation in citations:
            store.put_equity_signal_citation(
                EquitySignalCitation(
                    signal_id=signal_id,
                    source_type=citation["source_type"],
                    source_id=citation["source_id"],
                    quoted_span=citation["quoted_span"],
                    support_label=ForecastSupportLabel(citation["support_label"]),
                )
            )
        return SignalOutcome.PUBLISHED
