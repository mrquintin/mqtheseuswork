"""Opinion generator (prompt 05).

Given a ``CurrentEvent`` that has already passed the relevance gate (prompt 03)
and has retrieval hits (prompt 04), synthesize an ``EventOpinion`` plus its
``OpinionCitation`` rows via a single LLM call. The generator is a *citation
firewall*: every write is gated on a substring check against the source's
stored body, and any hallucinated source id or fabricated quote causes the
event to be marked ABSTAINED rather than published.

Public surface:

- ``generate_opinion(store, event, *, budget, ...) -> OpinionOutcome``
- ``OpinionOutcome`` (enum)

This module does NOT import the Anthropic or OpenAI SDKs directly — all LLM
traffic flows through ``noosphere.currents._llm_client.chat_json`` which in
turn routes through ``noosphere.llm.LLMClient``.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from noosphere.currents._llm_client import LLMError, LLMReply, chat_json, estimate_tokens
from noosphere.currents._opinion_prompts import (
    OPINION_SYSTEM_PROMPT,
    OPINION_USER_TEMPLATE,
    render_sources_block,
)
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.retrieval_adapter import EventRetrievalHit, retrieve_for_event
from noosphere.ids import make_citation_id, make_opinion_id
from noosphere.models import (
    CurrentEvent,
    CurrentEventStatus,
    EventOpinion,
    OpinionCitation,
    OpinionStance,
)
from noosphere.observability import get_logger
from noosphere.store import Store

logger = get_logger(__name__)


# Caps. These must match the prompt spec and the validation contract.
MAX_RAW_TEXT_CHARS = 3000
HEADLINE_MIN_CHARS = 30
HEADLINE_MAX_CHARS = 180
BODY_MAX_CHARS = 800
QUOTED_SPAN_MIN = 8
QUOTED_SPAN_MAX = 240
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_COMPLETION_TOKENS = 900
DEFAULT_MAX_RETRIES = 2


class OpinionOutcome(str, Enum):
    PUBLISHED = "PUBLISHED"
    ABSTAINED_BUDGET = "ABSTAINED_BUDGET"
    ABSTAINED_INSUFFICIENT_SOURCES = "ABSTAINED_INSUFFICIENT_SOURCES"
    ABSTAINED_NEAR_DUPLICATE = "ABSTAINED_NEAR_DUPLICATE"
    ABSTAINED_CITATION_FABRICATION = "ABSTAINED_CITATION_FABRICATION"


# ── prompt-injection defense ────────────────────────────────────────

def _sanitize_raw_text(text: str) -> str:
    """Run the shared ``PromptSeparator`` over the event's raw text.

    The separator was built to split founder-authored paragraphs from
    quoted/interviewer text; for X posts it's largely a no-op (short
    single-speaker text), but when a post embeds an "Ignore all prior
    instructions. …" line, the separator tags it as a prompt section and
    we drop it. A separator failure never breaks generation — we fall back
    to raw text and log ``prompt_separator_failed``.
    """
    if not text:
        return ""
    try:
        from noosphere.mitigations.prompt_separator import PromptSeparator

        separated = PromptSeparator().separate(text, source_type="written")
        # When the separator successfully identifies founder content, prefer
        # that. If it classified *everything* as prompt (unusual but possible
        # for a highly interrogative post), fall back to raw text so we don't
        # feed the LLM an empty event.
        if separated.founder_sections:
            return separated.founder_text
        return text
    except Exception as e:  # noqa: BLE001
        logger.warning("prompt_separator_failed", error=str(e))
        return text


# ── parsing ─────────────────────────────────────────────────────────

_JSON_BRACE_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """Parse JSON; fall through to a brace-grab if the model wrapped with text."""
    s = (text or "").strip()
    if not s:
        return None
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    m = _JSON_BRACE_RE.search(s)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        return None
    return None


_WS_RE = re.compile(r"\s+")


def _norm_ws(s: str) -> str:
    return _WS_RE.sub(" ", (s or "").strip()).casefold()


def _full_source_text(
    store: Store,
    *,
    source_kind: str,
    source_id: str,
    fallback: str,
) -> str:
    """Load the underlying Conclusion or Claim body from the store.

    Falls back to ``fallback`` (the truncated hit text) if the lookup fails,
    and logs ``citation_full_text_unavailable``.
    """
    try:
        if source_kind == "conclusion":
            obj = store.get_conclusion(source_id)
        elif source_kind == "claim":
            obj = store.get_claim(source_id)
        else:
            obj = None
        body = getattr(obj, "text", None) if obj is not None else None
        if body:
            return body
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "citation_full_text_unavailable",
            source_kind=source_kind,
            source_id=source_id,
            error=str(e),
        )
        return fallback
    logger.warning(
        "citation_full_text_unavailable",
        source_kind=source_kind,
        source_id=source_id,
    )
    return fallback


def _parse_and_validate(
    reply_text: str,
    hits: list[EventRetrievalHit],
    store: Store,
) -> tuple[bool, Any]:
    """Return (True, payload) on success, (False, reason_string) on failure."""
    payload = _extract_json(reply_text)
    if payload is None:
        return False, "invalid_json"

    # stance
    stance = payload.get("stance")
    if stance not in {"agrees", "disagrees", "complicates", "insufficient"}:
        return False, f"bad_stance:{stance!r}"

    # confidence
    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        return False, "bad_confidence_type"
    if not (0.0 <= confidence <= 1.0):
        return False, f"bad_confidence_range:{confidence}"

    # headline — only required for substantive stances. Insufficient stance
    # still needs some label but may legitimately be shorter.
    headline = (payload.get("headline") or "").strip()
    if "\n" in headline or "\r" in headline:
        return False, "headline_has_newline"
    if stance != "insufficient":
        if not (HEADLINE_MIN_CHARS <= len(headline) <= HEADLINE_MAX_CHARS):
            return False, f"bad_headline_length:{len(headline)}"

    # body_markdown
    body = (payload.get("body_markdown") or "").strip()
    if len(body) > BODY_MAX_CHARS:
        return False, f"body_too_long:{len(body)}"
    if stance != "insufficient" and not body:
        return False, "empty_body"

    # uncertainty_notes — optional, but must be a list of strings if present
    notes = payload.get("uncertainty_notes", [])
    if not isinstance(notes, list) or not all(isinstance(n, str) for n in notes):
        return False, "bad_uncertainty_notes"

    # citations
    citations = payload.get("citations", [])
    if not isinstance(citations, list):
        return False, "citations_not_list"

    if stance == "insufficient":
        if citations:
            return False, "insufficient_stance_with_citations"
        return True, payload

    if not citations:
        return False, "no_citations_for_substantive_stance"

    hit_index: dict[str, EventRetrievalHit] = {h.source_id: h for h in hits}
    for i, c in enumerate(citations):
        if not isinstance(c, dict):
            return False, f"citation_{i}_not_object"
        c_kind = c.get("source_kind")
        c_id = c.get("source_id")
        quoted = c.get("quoted_span")
        try:
            rel = float(c.get("relevance_score"))
        except (TypeError, ValueError):
            return False, f"citation_{i}_bad_relevance_type"
        if not (0.0 <= rel <= 1.0):
            return False, f"citation_{i}_bad_relevance_range"
        if c_kind not in {"conclusion", "claim"}:
            return False, f"citation_{i}_bad_kind:{c_kind!r}"
        if not isinstance(c_id, str) or c_id not in hit_index:
            return False, f"citation_{i}_hallucinated_source_id:{c_id!r}"
        hit = hit_index[c_id]
        if hit.source_kind != c_kind:
            return (
                False,
                f"citation_{i}_kind_mismatch:{c_kind}!={hit.source_kind}",
            )
        if not isinstance(quoted, str):
            return False, f"citation_{i}_bad_quote_type"
        q = quoted.strip()
        if not (QUOTED_SPAN_MIN <= len(q) <= QUOTED_SPAN_MAX):
            return False, f"citation_{i}_bad_quote_length:{len(q)}"
        # Verbatim substring check against the FULL stored body
        # (case-insensitive, whitespace-normalized).
        full = _full_source_text(
            store,
            source_kind=c_kind,
            source_id=c_id,
            fallback=hit.text,
        )
        if _norm_ws(q) not in _norm_ws(full):
            return False, f"citation_{i}_fabricated_quote"

    return True, payload


# ── building domain objects ─────────────────────────────────────────


def _to_opinion_and_citations(
    *,
    event: CurrentEvent,
    payload: dict[str, Any],
    hits: list[EventRetrievalHit],
    reply: LLMReply,
    model: str,
) -> tuple[EventOpinion, list[OpinionCitation]]:
    now = datetime.now(timezone.utc)
    gen_iso = now.isoformat()
    opinion_id = make_opinion_id(event.id, model, gen_iso)

    citations_in = payload.get("citations", []) or []
    citations: list[OpinionCitation] = []
    for ordinal, c in enumerate(citations_in):
        cid = make_citation_id(opinion_id, ordinal)
        c_kind = c["source_kind"]
        c_sid = c["source_id"]
        conclusion_id = c_sid if c_kind == "conclusion" else None
        claim_id = c_sid if c_kind == "claim" else None
        citations.append(
            OpinionCitation(
                id=cid,
                opinion_id=opinion_id,
                conclusion_id=conclusion_id,
                claim_id=claim_id,
                quoted_span=c["quoted_span"],
                relevance_score=float(c["relevance_score"]),
                ordinal=ordinal,
            )
        )

    stance = OpinionStance(payload["stance"])
    opinion = EventOpinion(
        id=opinion_id,
        event_id=event.id,
        generator_model=model,
        generated_at=now,
        stance=stance,
        confidence=float(payload["confidence"]),
        headline=(payload.get("headline") or "").strip(),
        body_markdown=(payload.get("body_markdown") or "").strip(),
        uncertainty_notes=list(payload.get("uncertainty_notes") or []),
        sources_considered=len(hits),
        sources_cited=len(citations),
        generator_tokens_prompt=int(reply.tokens_prompt),
        generator_tokens_completion=int(reply.tokens_completion),
    )
    return opinion, citations


# ── orchestrator ────────────────────────────────────────────────────


def _truncate_for_log(s: str, n: int = 200) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + "\u2026"


def generate_opinion(
    store: Store,
    event: CurrentEvent,
    *,
    budget: HourlyBudgetGuard,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> OpinionOutcome:
    """Generate and persist an opinion for ``event`` or mark it ABSTAINED.

    Preconditions:
    - ``event`` has already passed the prompt-03 relevance gate.
    - ``budget`` is the caller-owned hourly guard.

    Outcomes (see ``OpinionOutcome``) are mutually exclusive and always cause
    an event-status update as a side effect (except ``ABSTAINED_BUDGET``,
    which leaves the event in its existing status so the scheduler may retry
    in the next window).
    """
    hits = list(retrieve_for_event(store, event))
    if not hits:
        store.update_current_event_status(
            event.id,
            CurrentEventStatus.ABSTAINED,
            reason="no_sources_at_generation_time",
        )
        return OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES

    sanitized_text = _sanitize_raw_text(event.raw_text)
    user = OPINION_USER_TEMPLATE.format(
        source_url=event.source_url,
        author_handle=event.source_author_handle,
        captured_at_iso=event.source_captured_at.isoformat(),
        topic_hint=event.topic_hint or "(none)",
        raw_text=sanitized_text[:MAX_RAW_TEXT_CHARS],
        sources_block=render_sources_block(hits),
    )

    est_prompt = estimate_tokens(OPINION_SYSTEM_PROMPT) + estimate_tokens(user)
    est_completion = DEFAULT_COMPLETION_TOKENS
    if not budget.may_spend(est_prompt, est_completion):
        logger.warning(
            "opinion_budget_exhausted",
            event_id=event.id,
            est_prompt=est_prompt,
            est_completion=est_completion,
        )
        return OpinionOutcome.ABSTAINED_BUDGET

    last_error: Optional[str] = None
    for attempt in range(max_retries + 1):
        try:
            reply = chat_json(
                system=OPINION_SYSTEM_PROMPT,
                user=user,
                model=model,
                max_tokens=est_completion,
                api_key=api_key,
            )
        except LLMError as e:
            last_error = f"llm_error:{e}"
            logger.warning(
                "opinion_llm_error",
                event_id=event.id,
                attempt=attempt,
                error=str(e),
            )
            continue

        # Record token usage for every call (even invalid replies cost money).
        budget.record(reply.tokens_prompt, reply.tokens_completion)

        logger.info(
            "opinion_llm_reply",
            event_id=event.id,
            attempt=attempt,
            reply_preview=_truncate_for_log(reply.text, 200),
            tokens_prompt=reply.tokens_prompt,
            tokens_completion=reply.tokens_completion,
        )

        ok, payload_or_err = _parse_and_validate(reply.text, hits, store)
        if ok:
            payload = payload_or_err
            if payload.get("stance") == "insufficient":
                store.update_current_event_status(
                    event.id,
                    CurrentEventStatus.ABSTAINED,
                    reason="opinion_insufficient",
                )
                return OpinionOutcome.ABSTAINED_INSUFFICIENT_SOURCES
            opinion, citations = _to_opinion_and_citations(
                event=event,
                payload=payload,
                hits=hits,
                reply=reply,
                model=model,
            )
            store.add_event_opinion(opinion, citations)
            store.update_current_event_status(
                event.id, CurrentEventStatus.OPINED, reason=None
            )
            return OpinionOutcome.PUBLISHED
        last_error = payload_or_err
        logger.warning(
            "opinion_validation_failed",
            event_id=event.id,
            attempt=attempt,
            reason=_truncate_for_log(str(last_error), 200),
        )

    store.update_current_event_status(
        event.id,
        CurrentEventStatus.ABSTAINED,
        reason=f"opinion_validation_failed:{str(last_error or '')[:120]}",
    )
    return OpinionOutcome.ABSTAINED_CITATION_FABRICATION
