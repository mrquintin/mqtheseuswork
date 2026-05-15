"""Equity-signal retrieval adapter over the shared Noosphere retrieval path.

This adapter retrieves grounding sources for an EquityInstrument from the
same Noosphere index as Currents and Forecasts, but with stricter rules:

* principles outrank plain conclusions, which outrank raw claims;
* principles whose ``domain_of_applicability`` does not match the
  instrument's sector / asset class are dropped (fuzzy match);
* non-PUBLIC visibility requires ``surfaceable=True``;
* MMR with lambda=0.7 diversifies the final set.

It never raises: on error it logs ``equities.retrieval.error`` and
returns an empty list. The signal generator treats an empty list as
``ABSTAINED_INSUFFICIENT_PRINCIPLES``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from noosphere.currents.retrieval_adapter import retrieve_for_event
from noosphere.models import Claim, Conclusion, EquityInstrument
from noosphere.observability import get_logger

log = get_logger(__name__)

SourceType = Literal["PRINCIPLE", "CONCLUSION", "CLAIM"]
Visibility = Literal["PUBLIC", "FOUNDER", "INTERNAL"]

DEFAULT_TOP_K = 10
RETRIEVAL_OVERSAMPLE = 4
MAX_CANDIDATES = 40
MAX_SOURCE_AGE = timedelta(days=18 * 31)
MMR_LAMBDA = 0.7
PRINCIPLE_SCORE_BOOST = 0.10


@dataclass(frozen=True)
class RetrievedEquitySource:
    source_type: SourceType
    source_id: str
    text: str
    relevance: float
    surfaceable: bool
    visibility: Visibility
    domain_of_applicability: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _InstrumentRetrievalEvent:
    text: str
    topic_hint: str | None = None
    embedding: bytes | None = None


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _get_attr(source: Any, name: str, default: Any = None) -> Any:
    if hasattr(source, name):
        return getattr(source, name)
    extra = getattr(source, "model_extra", None)
    if isinstance(extra, dict) and name in extra:
        return extra[name]
    pydantic_extra = getattr(source, "__pydantic_extra__", None)
    if isinstance(pydantic_extra, dict) and name in pydantic_extra:
        return pydantic_extra[name]
    if isinstance(source, dict):
        return source.get(name, default)
    return default


def build_query_from_instrument(instrument: EquityInstrument) -> str:
    """Compose a query string from symbol, name, sector, and optional news blurb.

    ``sector`` and ``recent_news_blurb`` are looked up via attribute lookup so
    a future ingestor can attach them without changing the row schema.
    """

    symbol = _clean(getattr(instrument, "symbol", ""))
    name = _clean(getattr(instrument, "name", ""))
    asset_class = _get_attr(instrument, "asset_class", "")
    asset_class_str = _clean(getattr(asset_class, "value", asset_class))
    sector = _clean(_get_attr(instrument, "sector", ""))
    blurb = _clean(_get_attr(instrument, "recent_news_blurb", ""))

    lines = [
        f"{symbol} {name}".strip(),
        f"Asset class: {asset_class_str}" if asset_class_str else "",
        f"Sector: {sector}" if sector else "",
    ]
    if blurb:
        lines.append(f"Recent: {blurb[:600]}")
    return "\n\n".join(line for line in lines if line)


def retrieve_for_instrument(
    store: Any,
    instrument: EquityInstrument,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[RetrievedEquitySource]:
    """Retrieve grounding sources for one EquityInstrument.

    Returns at most ``top_k`` sources after filtering, principle-boosting, and
    MMR. Never raises; on error returns ``[]`` and emits a structured log.
    """

    if top_k <= 0:
        return []

    query = build_query_from_instrument(instrument)
    sector = _clean(_get_attr(instrument, "sector", ""))
    asset_class = _get_attr(instrument, "asset_class", "")
    asset_class_str = _clean(getattr(asset_class, "value", asset_class))

    event = _InstrumentRetrievalEvent(
        text=query,
        topic_hint=sector or asset_class_str or None,
    )
    retrieval_k = min(max(top_k * RETRIEVAL_OVERSAMPLE, top_k), MAX_CANDIDATES)

    try:
        hits = retrieve_for_event(store, event, top_k=retrieval_k)
        sources: list[RetrievedEquitySource] = []
        seen: set[tuple[str, str]] = set()
        for hit in hits:
            source = _source_from_hit(
                store,
                hit,
                instrument_sector=sector,
                instrument_asset_class=asset_class_str,
            )
            if source is None:
                continue
            key = (source.source_type, source.source_id)
            if key in seen:
                continue
            seen.add(key)
            sources.append(source)
        return _mmr_select(sources, query, top_k=top_k)
    except Exception as exc:
        log.warning(
            "equities.retrieval.error",
            instrument_id=getattr(instrument, "id", ""),
            symbol=getattr(instrument, "symbol", ""),
            error=str(exc),
        )
        return []


def _source_from_hit(
    store: Any,
    hit: Any,
    *,
    instrument_sector: str,
    instrument_asset_class: str,
) -> RetrievedEquitySource | None:
    source_kind = str(getattr(hit, "source_kind", "")).lower()
    source_id = str(getattr(hit, "source_id", ""))
    base_score = float(getattr(hit, "score", 0.0) or 0.0)

    if source_kind == "conclusion":
        conclusion = _get_conclusion(store, source_id)
        if conclusion is None or _is_revoked(conclusion):
            return None
        is_principle = _has_principle_kind(conclusion)
        if is_principle and not _domain_matches(
            conclusion,
            instrument_sector=instrument_sector,
            instrument_asset_class=instrument_asset_class,
        ):
            return None
        score = base_score + (PRINCIPLE_SCORE_BOOST if is_principle else 0.0)
        source_type: SourceType = "PRINCIPLE" if is_principle else "CONCLUSION"
        return _to_retrieved_source(
            source_type=source_type,
            source_id=source_id,
            text=str(getattr(hit, "text", getattr(conclusion, "text", ""))),
            relevance=score,
            source=conclusion,
        )
    if source_kind == "claim":
        claim = store.get_claim(source_id) if hasattr(store, "get_claim") else None
        if claim is None:
            return None
        return _to_retrieved_source(
            source_type="CLAIM",
            source_id=source_id,
            text=str(getattr(hit, "text", getattr(claim, "text", ""))),
            relevance=base_score,
            source=claim,
        )
    return None


def _has_principle_kind(conclusion: Any) -> bool:
    raw = _get_attr(conclusion, "principle_kind", None)
    if raw is None:
        return False
    if hasattr(raw, "value"):
        return bool(str(raw.value).strip())
    return bool(str(raw).strip())


def _domain_matches(
    conclusion: Any,
    *,
    instrument_sector: str,
    instrument_asset_class: str,
) -> bool:
    """Fuzzy match the principle's domain string against the instrument.

    The domain string is the founder-approved free-text on the principle.
    A match counts when any non-trivial token of the instrument's
    sector/asset-class appears (case-insensitive substring) in the
    domain, or vice-versa, or when the domain is empty (legacy rows are
    treated as universal so we do not silently drop founder-approved
    principles created before the prompt-56 fields landed).
    """

    domain = _clean(_get_attr(conclusion, "domain_of_applicability", ""))
    if not domain:
        return True
    targets = [instrument_sector.lower(), instrument_asset_class.lower()]
    targets = [t for t in targets if t]
    if not targets:
        return True
    lower_domain = domain.lower()
    for target in targets:
        if target in lower_domain or lower_domain in target:
            return True
        if any(token in lower_domain for token in _tokens(target) if len(token) >= 4):
            return True
        if any(token in target for token in _tokens(lower_domain) if len(token) >= 4):
            return True
    return False


def _get_conclusion(store: Any, conclusion_id: str) -> Conclusion | None:
    if hasattr(store, "get_conclusion"):
        conclusion = store.get_conclusion(conclusion_id)
        if conclusion is not None:
            return conclusion
    if hasattr(store, "list_conclusions"):
        for conclusion in store.list_conclusions():
            if str(getattr(conclusion, "id", "")) == conclusion_id:
                return conclusion
    return None


def _to_retrieved_source(
    *,
    source_type: SourceType,
    source_id: str,
    text: str,
    relevance: float,
    source: Conclusion | Claim,
) -> RetrievedEquitySource | None:
    visibility = _visibility_for(source, source_type)
    surfaceable = _surfaceable_for(source, visibility)
    if visibility != "PUBLIC" and not surfaceable:
        return None
    if _is_stale(source):
        return None
    domain = _clean(_get_attr(source, "domain_of_applicability", "")) or None
    return RetrievedEquitySource(
        source_type=source_type,
        source_id=source_id,
        text=text,
        relevance=max(0.0, min(1.0 + PRINCIPLE_SCORE_BOOST, relevance)),
        surfaceable=surfaceable,
        visibility=visibility,
        domain_of_applicability=domain,
        metadata=_metadata_for(source, source_type),
    )


def _literal_name(value: Any) -> str:
    if hasattr(value, "name"):
        return str(value.name).upper()
    if hasattr(value, "value"):
        return str(value.value).upper()
    return str(value or "").upper()


def _visibility_for(source: Any, source_type: SourceType) -> Visibility:
    explicit = _literal_name(_get_attr(source, "visibility", ""))
    if explicit in {"PUBLIC", "FOUNDER", "INTERNAL"}:
        return explicit  # type: ignore[return-value]

    if source_type == "CLAIM":
        origin = _literal_name(_get_attr(source, "claim_origin", ""))
        if origin in {"FOUNDER", "INTERNAL"}:
            return origin  # type: ignore[return-value]
        return "PUBLIC"

    confidence_tier = _literal_name(_get_attr(source, "confidence_tier", ""))
    if confidence_tier == "FOUNDER":
        return "FOUNDER"
    return "PUBLIC"


def _surfaceable_for(source: Any, visibility: Visibility) -> bool:
    raw = _get_attr(source, "surfaceable", None)
    if raw is not None:
        return bool(raw)
    public_safe = _get_attr(source, "public_safe", None)
    if public_safe is not None:
        return bool(public_safe)
    return visibility == "PUBLIC"


def _is_revoked(source: Any) -> bool:
    if bool(_get_attr(source, "is_revoked", False)):
        return True
    if _get_attr(source, "revoked_at", None) is not None:
        return True
    if _get_attr(source, "revokedAt", None) is not None:
        return True
    return False


def _is_stale(source: Any) -> bool:
    if bool(_get_attr(source, "is_load_bearing", False)):
        return False
    created = _source_datetime(source)
    if created is None:
        return False
    return _utc_now() - created > MAX_SOURCE_AGE


def _source_datetime(source: Any) -> datetime | None:
    for field_name in (
        "created_at",
        "createdAt",
        "episode_date",
        "updated_at",
        "updatedAt",
    ):
        value = _get_attr(source, field_name, None)
        if isinstance(value, datetime):
            return _as_utc(value)
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _metadata_for(source: Any, source_type: SourceType) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source_type": source_type}
    for field_name in (
        "principle_kind",
        "domain_of_applicability",
        "quantifiable_proxies",
        "confidence_tier",
        "claim_origin",
        "is_load_bearing",
        "disciplines",
    ):
        value = _get_attr(source, field_name, None)
        if value is None or value == [] or value == "":
            continue
        metadata[field_name] = _serializable(value)
    return metadata


def _serializable(value: Any) -> Any:
    if isinstance(value, list):
        return [_serializable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, (str, int, float, bool, dict)):
        return value
    return str(value)


def _mmr_select(
    sources: list[RetrievedEquitySource],
    query: str,
    *,
    top_k: int,
) -> list[RetrievedEquitySource]:
    if len(sources) <= top_k:
        return sorted(sources, key=_rank_key)[:top_k]

    selected: list[RetrievedEquitySource] = []
    remaining = sorted(sources, key=_rank_key)
    query_terms = _tokens(query)
    while remaining and len(selected) < top_k:
        best = max(
            remaining,
            key=lambda source: _mmr_score(source, selected, query_terms),
        )
        selected.append(best)
        remaining.remove(best)
    return selected


def _mmr_score(
    source: RetrievedEquitySource,
    selected: list[RetrievedEquitySource],
    query_terms: set[str],
) -> float:
    query_similarity = max(
        source.relevance, _jaccard(_tokens(source.text), query_terms)
    )
    if not selected:
        return query_similarity
    diversity_penalty = max(
        _jaccard(_tokens(source.text), _tokens(chosen.text)) for chosen in selected
    )
    return MMR_LAMBDA * query_similarity - (1.0 - MMR_LAMBDA) * diversity_penalty


def _rank_key(source: RetrievedEquitySource) -> tuple[float, int, str]:
    type_rank = {"PRINCIPLE": 0, "CONCLUSION": 1, "CLAIM": 2}.get(
        source.source_type, 3
    )
    return (-source.relevance, type_rank, source.source_id)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in "".join(
            ch.lower() if ch.isalnum() else " " for ch in str(text)
        ).split()
        if len(token) >= 3
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
