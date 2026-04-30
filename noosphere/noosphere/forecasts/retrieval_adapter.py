"""Forecast retrieval adapter over the shared Noosphere retrieval path.

The Forecasts pipeline retrieves from the same Noosphere index as Currents,
but its inputs and stricter surfacing rules differ. Centralizing this wrapper
means a future change to Currents-side retrieval cannot silently weaken
Forecasts-side surfacing -- the filter is enforced here, post-retrieval, where
Forecasts owns it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from noosphere.currents.retrieval_adapter import retrieve_for_event
from noosphere.models import Claim, Conclusion, ForecastMarket
from noosphere.observability import get_logger

log = get_logger(__name__)

SourceType = Literal["CONCLUSION", "CLAIM"]
Visibility = Literal["PUBLIC", "FOUNDER", "INTERNAL"]

DEFAULT_TOP_K = 8
RETRIEVAL_OVERSAMPLE = 4
MAX_CANDIDATES = 40
MAX_SOURCE_AGE = timedelta(days=18 * 31)
MMR_LAMBDA = 0.7


@dataclass(frozen=True)
class RetrievedSource:
    source_type: SourceType
    source_id: str
    text: str
    relevance: float
    surfaceable: bool
    visibility: Visibility
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _MarketRetrievalEvent:
    text: str
    topic_hint: str | None = None
    embedding: bytes | None = None


def _truncate(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def build_query_from_market(market: ForecastMarket) -> str:
    """
    Compose a single query string the embedding-side retriever can use.

    Recipe:
      title
      "\n\n"
      description (truncated to 600 chars)
      "\n\n"
      "Resolution criteria: " + resolutionCriteria (truncated to 400 chars)
      "\n\n"
      "Category: " + category
    """

    title = _clean(getattr(market, "title", ""))
    description = _truncate(getattr(market, "description", ""), 600)
    resolution_criteria = _truncate(
        getattr(
            market,
            "resolution_criteria",
            getattr(market, "resolutionCriteria", ""),
        ),
        400,
    )
    category = _clean(getattr(market, "category", ""))
    return (
        f"{title}\n\n"
        f"{description}\n\n"
        f"Resolution criteria: {resolution_criteria}\n\n"
        f"Category: {category}"
    )


def retrieve_for_market(
    store: Any,
    market: ForecastMarket,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[RetrievedSource]:
    """
    Wrap Currents retrieval for Forecast markets.

    Filter rules:
      - drop sources with `visibility != PUBLIC` UNLESS source.surfaceable is True
      - drop revoked conclusions
      - drop sources older than 18 months unless `is_load_bearing` is True
      - apply MMR (maximal marginal relevance) with lambda=0.7 to diversify
      - return at most top_k sources

    On error: never raise. Return [] and emit a `forecasts.retrieval.error`
    structured log. The generator treats [] as INSUFFICIENT_SOURCES.
    """

    if top_k <= 0:
        return []

    query = build_query_from_market(market)
    event = _MarketRetrievalEvent(
        text=query,
        topic_hint=getattr(market, "category", None),
    )
    retrieval_k = min(max(top_k * RETRIEVAL_OVERSAMPLE, top_k), MAX_CANDIDATES)

    try:
        hits = retrieve_for_event(store, event, top_k=retrieval_k)
        sources: list[RetrievedSource] = []
        seen: set[tuple[str, str]] = set()
        for hit in hits:
            source = _source_from_hit(store, hit)
            if source is None:
                continue
            key = (source.source_type, source.source_id)
            if key in seen:
                continue
            seen.add(key)
            sources.append(source)
        return _mmr_select(sources, query, top_k=top_k)
    except Exception as exc:  # pragma: no cover - exercised via tests.
        log.warning(
            "forecasts.retrieval.error",
            market_id=getattr(market, "id", ""),
            error=str(exc),
        )
        return []


def _source_from_hit(store: Any, hit: Any) -> RetrievedSource | None:
    source_kind = str(getattr(hit, "source_kind", "")).lower()
    source_id = str(getattr(hit, "source_id", ""))
    if source_kind == "conclusion":
        conclusion = _get_conclusion(store, source_id)
        if conclusion is None or _is_revoked(conclusion):
            return None
        return _to_retrieved_source(
            source_type="CONCLUSION",
            source_id=source_id,
            text=str(getattr(hit, "text", getattr(conclusion, "text", ""))),
            relevance=float(getattr(hit, "score", 0.0)),
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
            relevance=float(getattr(hit, "score", 0.0)),
            source=claim,
        )
    return None


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
) -> RetrievedSource | None:
    visibility = _visibility_for(source, source_type)
    surfaceable = _surfaceable_for(source, visibility)
    if visibility != "PUBLIC" and not surfaceable:
        return None
    if _is_stale(source):
        return None
    return RetrievedSource(
        source_type=source_type,
        source_id=source_id,
        text=text,
        relevance=max(0.0, min(1.0, relevance)),
        surfaceable=surfaceable,
        visibility=visibility,
        metadata=_metadata_for(source, source_type),
    )


def _field(source: Any, name: str, default: Any = None) -> Any:
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


def _literal_name(value: Any) -> str:
    if hasattr(value, "name"):
        return str(value.name).upper()
    if hasattr(value, "value"):
        return str(value.value).upper()
    return str(value or "").upper()


def _visibility_for(source: Any, source_type: SourceType) -> Visibility:
    explicit = _literal_name(_field(source, "visibility", ""))
    if explicit in {"PUBLIC", "FOUNDER", "INTERNAL"}:
        return explicit  # type: ignore[return-value]

    if source_type == "CLAIM":
        origin = _literal_name(_field(source, "claim_origin", ""))
        if origin in {"FOUNDER", "INTERNAL"}:
            return origin  # type: ignore[return-value]
        return "PUBLIC"

    confidence_tier = _literal_name(_field(source, "confidence_tier", ""))
    if confidence_tier == "FOUNDER":
        return "FOUNDER"
    return "PUBLIC"


def _surfaceable_for(source: Any, visibility: Visibility) -> bool:
    raw = _field(source, "surfaceable", None)
    if raw is not None:
        return bool(raw)
    public_safe = _field(source, "public_safe", None)
    if public_safe is not None:
        return bool(public_safe)
    return visibility == "PUBLIC"


def _is_revoked(source: Any) -> bool:
    if bool(_field(source, "is_revoked", False)):
        return True
    if _field(source, "revoked_at", None) is not None:
        return True
    if _field(source, "revokedAt", None) is not None:
        return True
    return False


def _is_stale(source: Any) -> bool:
    if bool(_field(source, "is_load_bearing", False)):
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
        value = _field(source, field_name, None)
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
    metadata: dict[str, Any] = {
        "source_type": source_type,
    }
    for field_name in (
        "disciplines",
        "confidence",
        "confidence_tier",
        "principles_used",
        "claims_used",
        "claim_origin",
        "source_id",
        "chunk_id",
        "evidence_pointers",
        "is_load_bearing",
    ):
        value = _field(source, field_name, None)
        if value is None:
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
    sources: list[RetrievedSource],
    query: str,
    *,
    top_k: int,
) -> list[RetrievedSource]:
    if len(sources) <= top_k:
        return sorted(sources, key=_rank_key)[:top_k]

    selected: list[RetrievedSource] = []
    remaining = sorted(sources, key=_rank_key)
    query_terms = _terms(query)
    while remaining and len(selected) < top_k:
        best = max(
            remaining,
            key=lambda source: _mmr_score(source, selected, query_terms),
        )
        selected.append(best)
        remaining.remove(best)
    return selected


def _mmr_score(
    source: RetrievedSource,
    selected: list[RetrievedSource],
    query_terms: set[str],
) -> float:
    query_similarity = max(source.relevance, _jaccard(_terms(source.text), query_terms))
    if not selected:
        return query_similarity
    diversity_penalty = max(
        _jaccard(_terms(source.text), _terms(chosen.text)) for chosen in selected
    )
    return MMR_LAMBDA * query_similarity - (1.0 - MMR_LAMBDA) * diversity_penalty


def _rank_key(source: RetrievedSource) -> tuple[float, int, str]:
    return (
        -source.relevance,
        0 if source.source_type == "CONCLUSION" else 1,
        source.source_id,
    )


def _terms(text: str) -> set[str]:
    return {
        token
        for token in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
        if len(token) >= 3
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
