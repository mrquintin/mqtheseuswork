"""Longform article generation on top of the public PublishedConclusion table."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlmodel import desc, select

from noosphere.currents._llm_client import LLMResponse, make_client
from noosphere.currents.budget import BudgetExhausted
from noosphere.currents.opinion_generator import _estimate_tokens, _extract_json_object
from noosphere.models import (
    EventOpinion,
    ForecastBet,
    ForecastPrediction,
    ForecastResolution,
    OpinionCitation,
    PublishedConclusion,
    ReviewItem,
)


class ArticleKind(str, Enum):
    THEMATIC = "THEMATIC"
    POSTMORTEM = "POSTMORTEM"
    CORRECTION = "CORRECTION"


@dataclass(frozen=True)
class ArticleCitation:
    source_kind: str
    source_id: str
    quoted_span: str
    public_url: str | None = None


@dataclass(frozen=True)
class Article:
    id: str
    slug: str
    kind: ArticleKind
    headline: str
    body_markdown: str
    source_ids: list[str]
    citations: list[ArticleCitation]
    published_at: datetime
    status: str = "published"
    review_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SourceBlock:
    source_kind: str
    source_id: str
    organization_id: str
    topic_hint: str | None
    text: str
    public_url: str | None = None


ARTICLE_MAX_TOKENS = 2_600
MAX_TITLE_CHARS = 70
MIN_THEMATIC_PRIOR_CONCLUSION_CITATIONS = 3
MAX_JSON_FAILURES = 3
MAX_CITATION_FAILURES = 2
MAX_BODY_FAILURES = 2
MAX_TITLE_REVISIONS = 1
MAX_OPENING_REVISIONS = 1
FIRM_VOICE_RE = re.compile(r"\bthe\s+firm\b", re.IGNORECASE)
SOURCE_RECAP_RE = re.compile(
    r"(?im)(^\s{0,3}#{1,6}\s*(retrieved\s+)?(source|sources|transcript|essay)\b|^\s*\[SOURCE\s+\d+\])"
)
PUBLIC_RELATIVE_PATH_RE = re.compile(r"^/(?:c|post|currents|forecasts)(?:/|$)")
OPENING_DENYLIST_PROMPT = "article_opening_denylist.md"


def _prompt_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "_prompts" / name


def _read_system_prompt(name: str) -> str:
    return _prompt_path(name).read_text(encoding="utf-8").strip()


def _read_opening_denylist() -> tuple[str, ...]:
    try:
        raw = _prompt_path(OPENING_DENYLIST_PROMPT).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()

    phrases: list[str] = []
    for line in raw.splitlines():
        phrase = line.strip()
        if not phrase or phrase.startswith("#"):
            continue
        if phrase.startswith(("-", "*")):
            phrase = phrase[1:].strip()
        phrase = phrase.strip("\"'` ")
        if phrase:
            phrases.append(phrase)
    return tuple(phrases)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _charge_budget(budget: Any, response: LLMResponse) -> None:
    charge = getattr(budget, "charge", None)
    if callable(charge):
        charge(response.prompt_tokens, response.completion_tokens)


def _authorize_budget(budget: Any, *, system: str, user: str) -> None:
    authorize = getattr(budget, "authorize", None)
    if callable(authorize):
        authorize(_estimate_tokens(system, user), ARTICLE_MAX_TOKENS)


def _slugify(text: str, max_len: int = 84) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or "theseus-article")[:max_len].strip("-") or "theseus-article"


def _first_paragraph(body_markdown: str) -> str:
    for block in re.split(r"\n\s*\n", body_markdown.strip()):
        candidate = block.strip()
        if candidate:
            return re.sub(r"\s+", " ", candidate)
    return ""


def _generic_opening_hit(body_markdown: str) -> str | None:
    first = _first_paragraph(body_markdown)
    if not first:
        return None
    normalized = first.lstrip("#> -*\t").lower()
    for phrase in _read_opening_denylist():
        candidate = phrase.rstrip(".").lower()
        if re.match(rf"^{re.escape(candidate)}(?:\b|[,.!?;:])", normalized):
            return phrase
    return None


def _source_key(kind: ArticleKind, source_ids: list[str]) -> str:
    canonical = json.dumps(
        {"kind": kind.value, "source_ids": sorted(source_ids)},
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _source_blocks_text(sources: list[_SourceBlock]) -> str:
    blocks: list[str] = []
    for idx, source in enumerate(sources, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[SOURCE {idx}]",
                    f"source_kind: {source.source_kind}",
                    f"source_id: {source.source_id}",
                    f"organization_id: {source.organization_id}",
                    f"topic_hint: {source.topic_hint or ''}",
                    "text:",
                    source.text,
                    f"[/SOURCE {idx}]",
                ]
            )
        )
    return "\n\n".join(blocks)


def _public_url(value: str | None) -> str | None:
    url = (value or "").strip()
    if not url:
        return None
    if url.startswith("https://"):
        return url
    if PUBLIC_RELATIVE_PATH_RE.match(url):
        return url
    return None


def _article_user_prompt(
    kind: ArticleKind, source_ids: list[str], sources: list[_SourceBlock]
) -> str:
    return "\n\n".join(
        [
            "ARTICLE REQUEST",
            f"kind: {kind.value}",
            f"source_ids: {json.dumps(source_ids)}",
            "RETRIEVED THESEUS SOURCES",
            _source_blocks_text(sources),
            "Return the strict JSON object specified by the system prompt.",
        ]
    )


def _topic_hint(payload: dict[str, Any], sources: list[_SourceBlock]) -> str:
    raw = str(payload.get("topic_hint") or "").strip()
    if raw:
        return re.sub(r"[^a-z0-9_]+", "_", raw.lower()).strip("_")[:48] or "article"
    for source in sources:
        if source.topic_hint:
            return (
                re.sub(r"[^a-z0-9_]+", "_", source.topic_hint.lower()).strip("_")[:48]
                or "article"
            )
    return "article"


def _confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, parsed))


def _string(value: Any, fallback: str = "") -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _source_text_for_current_event(store: Any, source_id: str) -> _SourceBlock | None:
    event = store.get_current_event(source_id)
    if event is None:
        return None
    return _SourceBlock(
        source_kind="current_event",
        source_id=event.id,
        organization_id=event.organization_id,
        topic_hint=event.topic_hint,
        public_url=_public_url(event.url),
        text="\n".join(
            [
                f"Current event: {event.text}",
                f"Observed at: {event.observed_at.isoformat()}",
                f"External id: {event.external_id}",
                f"URL: {event.url or ''}",
            ]
        ),
    )


def _source_text_for_opinion(store: Any, source_id: str) -> _SourceBlock | None:
    opinion = store.get_event_opinion(source_id)
    if opinion is None:
        return None
    event = store.get_current_event(opinion.event_id)
    revoked = (
        f" Revoked reason: {opinion.revoked_reason}" if opinion.revoked_reason else ""
    )
    return _SourceBlock(
        source_kind="event_opinion",
        source_id=opinion.id,
        organization_id=opinion.organization_id,
        topic_hint=opinion.topic_hint,
        public_url=f"/currents/{opinion.id}",
        text="\n".join(
            [
                f"Opinion headline: {opinion.headline}",
                f"Opinion stance: {_enum_value(opinion.stance)}",
                f"Opinion confidence: {opinion.confidence:.3f}",
                f"Opinion body: {opinion.body_markdown}",
                f"Underlying event: {event.text if event is not None else ''}",
                f"Revoked at: {opinion.revoked_at.isoformat() if opinion.revoked_at else ''}{revoked}",
            ]
        ),
    )


def _source_text_for_postmortem(store: Any, prediction_id: str) -> _SourceBlock | None:
    prediction = store.get_forecast_prediction(prediction_id)
    if prediction is None:
        return None
    resolution = store.get_forecast_resolution(prediction_id)
    if resolution is None:
        return None
    bets = store.list_bets_for_prediction(prediction_id)
    stake_total = sum(float(getattr(bet, "stake_usd", 0) or 0) for bet in bets)
    return _SourceBlock(
        source_kind="forecast_postmortem",
        source_id=prediction.id,
        organization_id=prediction.organization_id,
        topic_hint=prediction.topic_hint,
        public_url=f"/forecasts/{prediction.id}",
        text="\n".join(
            [
                f"Forecast headline: {prediction.headline}",
                f"Prior probability YES: {prediction.probability_yes}",
                f"Realized outcome: {_enum_value(resolution.market_outcome)}",
                f"Brier score: {resolution.brier_score}",
                f"Log loss: {resolution.log_loss}",
                f"Resolution justification: {resolution.justification}",
                f"Total stake attached to prediction: {stake_total:.2f}",
                f"Forecast reasoning: {prediction.reasoning}",
            ]
        ),
    )


def _source_text_for_correction(store: Any, opinion_id: str) -> _SourceBlock | None:
    opinion = store.get_event_opinion(opinion_id)
    if opinion is None:
        return None
    citations = store.list_opinion_citations(opinion_id)
    revoked = [citation for citation in citations if citation.is_revoked]
    affected = ", ".join(
        f"{citation.source_kind}:{citation.conclusion_id or citation.claim_id or ''}"
        for citation in revoked
    )
    reasons = "; ".join(
        citation.revoked_reason or "source revoked" for citation in revoked
    )
    revoked_times = "; ".join(
        citation.revoked_at.isoformat()
        for citation in revoked
        if citation.revoked_at is not None
    )
    return _SourceBlock(
        source_kind="correction",
        source_id=opinion.id,
        organization_id=opinion.organization_id,
        topic_hint=opinion.topic_hint,
        public_url=f"/currents/{opinion.id}",
        text="\n".join(
            [
                f"Affected opinion: {opinion.headline}",
                f"Affected opinion id: {opinion.id}",
                f"Dependent opinion body: {opinion.body_markdown}",
                f"Revoked citations: {affected or 'none recorded'}",
                f"Revocation reasons: {reasons or opinion.revoked_reason or 'source revoked'}",
                f"Citation revoked at: {revoked_times or ''}",
                f"Opinion revoked at: {opinion.revoked_at.isoformat() if opinion.revoked_at else ''}",
            ]
        ),
    )


def _load_sources(
    store: Any, kind: ArticleKind, source_ids: list[str]
) -> list[_SourceBlock]:
    sources: list[_SourceBlock] = []
    for source_id in source_ids:
        source: _SourceBlock | None
        if kind == ArticleKind.THEMATIC:
            source = _source_text_for_current_event(
                store, source_id
            ) or _source_text_for_opinion(store, source_id)
        elif kind == ArticleKind.POSTMORTEM:
            source = _source_text_for_postmortem(store, source_id)
        else:
            source = _source_text_for_correction(
                store, source_id
            ) or _source_text_for_opinion(store, source_id)
        if source is not None:
            sources.append(source)
    return sources


def validate_article_citations(
    raw_citations: Any,
    sources: list[_SourceBlock],
    *,
    require_any: bool = True,
) -> tuple[list[ArticleCitation], list[str]]:
    if not isinstance(raw_citations, list):
        return [], ["citations must be a list"]

    by_pair = {(source.source_kind, source.source_id): source for source in sources}
    normalized: list[ArticleCitation] = []
    errors: list[str] = []
    for idx, raw in enumerate(raw_citations):
        if not isinstance(raw, dict):
            errors.append(f"citation {idx} is not an object")
            continue
        source_kind = str(raw.get("source_kind") or raw.get("sourceKind") or "").strip()
        source_id = str(raw.get("source_id") or raw.get("sourceId") or "").strip()
        quoted_span = raw.get("quoted_span") or raw.get("quotedSpan")
        if not source_kind or not source_id:
            errors.append(f"citation {idx} is missing source_kind/source_id")
            continue
        if not isinstance(quoted_span, str) or not quoted_span:
            errors.append(f"citation {idx} is missing quoted_span")
            continue
        source = by_pair.get((source_kind, source_id))
        if source is None:
            errors.append(f"citation {idx} cites an unretrieved source")
            continue
        if quoted_span not in source.text:
            errors.append(f"citation {idx} quoted_span is not a verbatim substring")
            continue
        normalized.append(
            ArticleCitation(source_kind, source_id, quoted_span, source.public_url)
        )

    if require_any and not normalized:
        errors.append("published articles require at least one valid citation")
    return normalized, errors


def validate_article_body(body_markdown: str) -> list[str]:
    errors: list[str] = []
    if not FIRM_VOICE_RE.search(body_markdown):
        errors.append(
            'body_markdown must explicitly use firm voice with the phrase "the firm"'
        )
    if SOURCE_RECAP_RE.search(body_markdown):
        errors.append(
            "body_markdown must not include raw source/transcript/essay recap sections"
        )
    return errors


def validate_article_headline(headline: str) -> list[str]:
    if len(headline.strip()) <= MAX_TITLE_CHARS:
        return []
    return [f"headline exceeds {MAX_TITLE_CHARS} characters"]


def validate_article_opening(body_markdown: str) -> list[str]:
    hit = _generic_opening_hit(body_markdown)
    if hit is None:
        return []
    return [f"first paragraph begins with generic opening {hit!r}"]


def _minimum_valid_citations(kind: ArticleKind, sources: list[_SourceBlock]) -> int:
    if (
        kind == ArticleKind.THEMATIC
        and len(sources) >= MIN_THEMATIC_PRIOR_CONCLUSION_CITATIONS
    ):
        return MIN_THEMATIC_PRIOR_CONCLUSION_CITATIONS
    return 1


def validate_article_citation_floor(
    citations: list[ArticleCitation],
    *,
    min_valid_citations: int,
) -> list[str]:
    if len(citations) >= min_valid_citations:
        return []
    return [
        "article must cite at least "
        f"{min_valid_citations} prior firm conclusions; got {len(citations)}"
    ]


def _article_payload(
    *,
    kind: ArticleKind,
    headline: str,
    body_markdown: str,
    topic_hint: str,
    source_ids: list[str],
    citations: list[ArticleCitation],
    published_at: datetime,
) -> dict[str, Any]:
    exit_conditions = [
        "A cited source is revoked or materially corrected.",
        "New retrieved sources change the article's main synthesis.",
    ]
    return {
        "schema": "theseus.publicConclusion.v1",
        "conclusionText": headline,
        "rationale": body_markdown,
        "topicHint": topic_hint,
        "evidenceSummary": body_markdown,
        "exitConditions": exit_conditions,
        "strongestObjection": {
            "objection": "The essay may overfit a narrow source window.",
            "firmAnswer": (
                "It is published with explicit source ids and verbatim citation "
                "spans so later corrections can be traced."
            ),
        },
        "openQuestionsAdjacent": [],
        "voiceComparisons": [],
        "timeline": [
            {
                "at": published_at.isoformat(),
                "label": f"{kind.value.title()} article generated",
            }
        ],
        "whatWouldChangeOurMind": exit_conditions,
        "citations": [],
        "article": {
            "kind": kind.value,
            "sourceIds": source_ids,
            "bodyMarkdown": body_markdown,
            "citations": [
                {
                    "label": f"S{idx}",
                    "source_kind": citation.source_kind,
                    "source_id": citation.source_id,
                    "quoted_span": citation.quoted_span,
                    "public_url": citation.public_url,
                    "linkable": bool(citation.public_url),
                }
                for idx, citation in enumerate(citations, start=1)
            ],
        },
    }


def _published_article_row_to_article(row: PublishedConclusion) -> Article:
    payload = json.loads(row.payload_json or "{}")
    article_payload = payload.get("article") if isinstance(payload, dict) else {}
    citations = []
    if isinstance(article_payload, dict):
        for raw in article_payload.get("citations") or []:
            if isinstance(raw, dict):
                citations.append(
                    ArticleCitation(
                        str(raw.get("source_kind") or ""),
                        str(raw.get("source_id") or ""),
                        str(raw.get("quoted_span") or ""),
                        _public_url(
                            str(raw.get("public_url") or raw.get("publicUrl") or "")
                        ),
                    )
                )
    kind_value = str(
        article_payload.get("kind") if isinstance(article_payload, dict) else ""
    )
    kind = (
        ArticleKind(kind_value)
        if kind_value in {item.value for item in ArticleKind}
        else ArticleKind.THEMATIC
    )
    return Article(
        id=row.id,
        slug=row.slug,
        kind=kind,
        headline=(
            str(payload.get("conclusionText") or row.slug)
            if isinstance(payload, dict)
            else row.slug
        ),
        body_markdown=(
            str(article_payload.get("bodyMarkdown") or payload.get("rationale") or "")
            if isinstance(article_payload, dict)
            else ""
        ),
        source_ids=(
            [str(item) for item in article_payload.get("sourceIds", [])]
            if isinstance(article_payload, dict)
            else []
        ),
        citations=citations,
        published_at=_as_utc(row.published_at),
        status=(
            str(article_payload.get("status") or "published")
            if isinstance(article_payload, dict)
            else "published"
        ),
    )


def _existing_article_for_key(
    store: Any, source_key: str
) -> PublishedConclusion | None:
    needle = f'"sourceKey": "{source_key}"'
    compact_needle = f'"sourceKey":"{source_key}"'
    with store.session() as session:
        rows = list(
            session.exec(
                select(PublishedConclusion)
                .where(PublishedConclusion.kind == "ARTICLE")
                .order_by(desc(PublishedConclusion.published_at))
                .limit(500)
            ).all()
        )
    for row in rows:
        if needle in row.payload_json or compact_needle in row.payload_json:
            return row
        try:
            payload = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        article_payload = payload.get("article") if isinstance(payload, dict) else None
        if (
            isinstance(article_payload, dict)
            and article_payload.get("sourceKey") == source_key
        ):
            return row
    return None


def article_already_published(
    store: Any, *, kind: ArticleKind, source_ids: list[str]
) -> bool:
    return _existing_article_for_key(store, _source_key(kind, source_ids)) is not None


def count_articles_since(store: Any, since: datetime) -> int:
    with store.session() as session:
        return len(
            list(
                session.exec(
                    select(PublishedConclusion.id)
                    .where(PublishedConclusion.kind == "ARTICLE")
                    .where(PublishedConclusion.published_at >= since)
                ).all()
            )
        )


def _unique_slug(store: Any, base_slug: str, source_key: str) -> str:
    slug = base_slug
    suffix = source_key[:8]
    with store.session() as session:
        existing = session.exec(
            select(PublishedConclusion.id)
            .where(PublishedConclusion.slug == slug)
            .limit(1)
        ).first()
        if existing is None:
            return slug
        slug = f"{base_slug[:72].rstrip('-')}-{suffix}"
        counter = 2
        while (
            session.exec(
                select(PublishedConclusion.id)
                .where(PublishedConclusion.slug == slug)
                .limit(1)
            ).first()
            is not None
        ):
            slug = f"{base_slug[:68].rstrip('-')}-{suffix}-{counter}"
            counter += 1
    return slug


def _persist_article(
    store: Any,
    *,
    kind: ArticleKind,
    headline: str,
    body_markdown: str,
    topic_hint: str,
    confidence: float,
    source_ids: list[str],
    citations: list[ArticleCitation],
    sources: list[_SourceBlock],
) -> Article:
    published_at = _utcnow()
    source_key = _source_key(kind, source_ids)
    base_slug = _slugify(headline)
    slug = _unique_slug(store, base_slug, source_key)
    payload = _article_payload(
        kind=kind,
        headline=headline,
        body_markdown=body_markdown,
        topic_hint=topic_hint,
        source_ids=source_ids,
        citations=citations,
        published_at=published_at,
    )
    payload["article"]["sourceKey"] = source_key
    payload["article"]["status"] = "published"
    organization_id = sources[0].organization_id if sources else "default"
    row = PublishedConclusion(
        organization_id=organization_id,
        source_conclusion_id=f"article:{source_key}",
        slug=slug,
        version=1,
        kind="ARTICLE",
        discounted_confidence=confidence,
        stated_confidence=confidence,
        calibration_discount_reason=(
            "Generated article confidence is source-grounded and not a reviewed "
            "firm conclusion confidence."
        ),
        payload_json=json.dumps(payload, sort_keys=True),
        doi="",
        zenodo_record_id="",
        published_at=published_at,
    )
    with store.session() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return _published_article_row_to_article(row)


def _queue_article_review_item(
    store: Any,
    *,
    kind: ArticleKind,
    source_key: str,
    headline: str,
    body_markdown: str,
    source_ids: list[str],
    reasons: list[str],
    created_at: datetime,
) -> None:
    put_review_item = getattr(store, "put_review_item", None)
    if not callable(put_review_item):
        return
    payload = {
        "status": "needs_review",
        "kind": kind.value,
        "headline": headline,
        "source_ids": source_ids,
        "reasons": reasons,
        "body_preview": body_markdown[:800],
    }
    put_review_item(
        ReviewItem(
            id=f"article_review:{source_key}",
            claim_a_id=f"article:{source_key}",
            claim_b_id="publication_quality_gate",
            reason=json.dumps(payload, sort_keys=True),
            status="open",
            created_at=created_at,
        )
    )


def _needs_review_article(
    store: Any,
    *,
    kind: ArticleKind,
    headline: str,
    body_markdown: str,
    source_ids: list[str],
    citations: list[ArticleCitation],
    reasons: list[str],
) -> Article:
    created_at = _utcnow()
    source_key = _source_key(kind, source_ids)
    _queue_article_review_item(
        store,
        kind=kind,
        source_key=source_key,
        headline=headline,
        body_markdown=body_markdown,
        source_ids=source_ids,
        reasons=reasons,
        created_at=created_at,
    )
    return Article(
        id=f"article_review:{source_key}",
        slug=_slugify(headline or "article-needs-review"),
        kind=kind,
        headline=headline,
        body_markdown=body_markdown,
        source_ids=source_ids,
        citations=citations,
        published_at=created_at,
        status="needs_review",
        review_reasons=tuple(reasons),
    )


async def generate_article(
    store: Any,
    *,
    kind: ArticleKind,
    source_ids: list[str],
    budget: Any,
) -> Article | None:
    """
    Compose and persist one public article as a PublishedConclusion row.

    Idempotency is by `(kind, sorted(source_ids))`, stored in payload metadata.
    """

    clean_source_ids = [
        source_id for source_id in dict.fromkeys(source_ids) if source_id
    ]
    if not clean_source_ids:
        return None
    if article_already_published(store, kind=kind, source_ids=clean_source_ids):
        existing = _existing_article_for_key(store, _source_key(kind, clean_source_ids))
        return _published_article_row_to_article(existing) if existing else None

    sources = _load_sources(store, kind, clean_source_ids)
    if not sources:
        return None

    base_system = _read_system_prompt("article_system.md")
    user_prompt = _article_user_prompt(kind, clean_source_ids, sources)
    corrective = ""
    json_failures = 0
    citation_failures = 0
    body_failures = 0
    title_failures = 0
    opening_failures = 0
    client = None

    while (
        json_failures < MAX_JSON_FAILURES
        and citation_failures < MAX_CITATION_FAILURES
        and body_failures < MAX_BODY_FAILURES
    ):
        system_prompt = base_system + corrective
        try:
            _authorize_budget(budget, system=system_prompt, user=user_prompt)
        except BudgetExhausted:
            return None

        if client is None:
            client = make_client()
        response = await client.complete(
            system=system_prompt,
            user=user_prompt,
            max_tokens=ARTICLE_MAX_TOKENS,
            temperature=0.0,
        )
        _charge_budget(budget, response)

        try:
            payload = _extract_json_object(response.text)
        except (json.JSONDecodeError, ValueError):
            json_failures += 1
            corrective = "\n\nCorrection: return only parseable strict JSON."
            continue

        headline = _string(payload.get("headline"), "Theseus article")[:180]
        body_markdown = _string(
            payload.get("body_markdown") or payload.get("bodyMarkdown")
        )
        if not body_markdown:
            json_failures += 1
            corrective = "\n\nCorrection: body_markdown is required."
            continue

        body_errors = validate_article_body(body_markdown)
        if body_errors:
            body_failures += 1
            if body_failures >= MAX_BODY_FAILURES:
                return None
            corrective = (
                "\n\nCorrection: the previous response violated the public article voice contract: "
                + "; ".join(body_errors[:3])
                + '. Rewrite as a synthesized firm perspective using the phrase "the firm", '
                "not as a recap of source material."
            )
            continue

        citations, citation_errors = validate_article_citations(
            payload.get("citations"), sources
        )
        if not citations:
            citation_failures += 1
            if citation_failures >= MAX_CITATION_FAILURES:
                return None
            corrective = (
                "\n\nCorrection: the previous response failed exact citation validation: "
                + "; ".join(citation_errors[:3])
                + ". Copy quoted_span exactly from the cited source text."
            )
            continue

        title_errors = validate_article_headline(headline)
        if title_errors:
            title_failures += 1
            if title_failures > MAX_TITLE_REVISIONS:
                return _needs_review_article(
                    store,
                    kind=kind,
                    headline=headline,
                    body_markdown=body_markdown,
                    source_ids=clean_source_ids,
                    citations=citations,
                    reasons=title_errors,
                )
            corrective = (
                "\n\nCorrection: the previous headline violated the title policy: "
                + "; ".join(title_errors)
                + f". Return a noun-phrase headline of {MAX_TITLE_CHARS} characters "
                "or fewer, with no terminal punctuation."
            )
            continue

        opening_errors = validate_article_opening(body_markdown)
        if opening_errors:
            opening_failures += 1
            if opening_failures > MAX_OPENING_REVISIONS:
                return _needs_review_article(
                    store,
                    kind=kind,
                    headline=headline,
                    body_markdown=body_markdown,
                    source_ids=clean_source_ids,
                    citations=citations,
                    reasons=opening_errors,
                )
            corrective = (
                "\n\nCorrection: the previous body violated the opening policy: "
                + "; ".join(opening_errors)
                + ". Start with a concrete Theseus claim or question, not a generic "
                "scene-setting phrase."
            )
            continue

        citation_floor_errors = validate_article_citation_floor(
            citations,
            min_valid_citations=_minimum_valid_citations(kind, sources),
        )
        if citation_floor_errors:
            return _needs_review_article(
                store,
                kind=kind,
                headline=headline,
                body_markdown=body_markdown,
                source_ids=clean_source_ids,
                citations=citations,
                reasons=citation_floor_errors,
            )

        return _persist_article(
            store,
            kind=kind,
            headline=headline,
            body_markdown=body_markdown,
            topic_hint=_topic_hint(payload, sources),
            confidence=_confidence(payload.get("confidence")),
            source_ids=clean_source_ids,
            citations=citations,
            sources=sources,
        )

    return None
