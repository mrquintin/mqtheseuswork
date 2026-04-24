"""Follow-up Q&A engine (prompt 06).

A public user reads an ``EventOpinion`` and opens a chat anchored to it.
Every question triggers a FRESH ``retrieve_for_event`` call — we never reuse
the opinion's citations as the sole grounding context, because the user's
question may be about a tangent we didn't cover in the opinion itself.
Answers stream via an async generator of ``FollowUpAnswerChunk`` values.

Security/safety invariants:

- The user's question is run through ``PromptSeparator`` before being embedded
  in the user prompt; the question is ALWAYS wrapped inside the QUESTION
  block and never allowed to bleed into the system-prompt region.
- Rate limits are checked BEFORE persisting the user message.
- The user message is persisted BEFORE the LLM call, so we have a record of
  the question even if the LLM errors.
- Citations emitted in ``[[CITE: ...]]`` tails are validated against freshly
  retrieved hits (kind match, id in hit set, quote verbatim). Invalid
  citations are silently discarded at INFO level — LLMs hallucinate.
- The follow-up engine never mutates the opinion or event state.
- One-shot LLM call per question — no retries (opinion generator retries;
  follow-up is interactive).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Optional

from noosphere.currents._followup_prompts import (
    FOLLOWUP_SYSTEM_PROMPT,
    FOLLOWUP_USER_TEMPLATE,
    render_sources_block,
)
from noosphere.currents._llm_client import (
    LLMError,
    LLMStreamChunk,
    chat_stream_text,
    estimate_tokens,
)
from noosphere.currents.budget import HourlyBudgetGuard
from noosphere.currents.retrieval_adapter import EventRetrievalHit, retrieve_for_event
from noosphere.ids import (
    make_followup_citation_id,
    make_followup_message_id,
    make_followup_session_id,
)
from noosphere.mitigations.prompt_separator import PromptSeparator
from noosphere.models import (
    CurrentEvent,
    EventOpinion,
    FollowUpMessage,
    FollowUpMessageRole,
    FollowUpSession,
    OpinionCitation,
)
from noosphere.observability import get_logger
from noosphere.store import Store


logger = get_logger(__name__)


RATE_LIMIT_PER_FINGERPRINT_PER_DAY = 20
RATE_LIMIT_PER_SESSION = 8
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_COMPLETION_TOKENS = 600
_MAX_PRIOR_TURNS = 6
_MAX_PRIOR_TURN_CHARS = 400
_MAX_QUESTION_CHARS = 800

# Citation parse regex. Matches:
#   [[CITE: source_kind=conclusion source_id=abc quoted="text..."]]
_CITE_RE = re.compile(
    r"\[\[CITE:\s*source_kind=(?P<kind>\w+)\s+source_id=(?P<sid>\S+)\s+"
    r'quoted="(?P<q>[^"]{0,512})"\s*\]\]',
    re.DOTALL,
)
_WS_RE = re.compile(r"\s+")


class RateLimitExceeded(RuntimeError):
    """Raised before any persistence when a rate limit is exceeded.

    ``.args[0]`` is a short machine-readable reason code:
    ``session_message_cap`` or ``daily_cap``.
    """


@dataclass
class FollowUpAnswerChunk:
    """Single yielded unit from ``answer_followup``.

    The stream emits zero or more chunks with ``done=False`` carrying
    ``text`` deltas, then a final chunk with ``done=True`` carrying
    validated citations (empty list on refusal). ``refused=True`` signals
    that the final chunk represents a terminal refusal (``refusal_reason``
    is the machine-readable code).
    """
    text: str = ""
    done: bool = False
    citations: list[OpinionCitation] = field(default_factory=list)
    refused: bool = False
    refusal_reason: Optional[str] = None


# ── fingerprint / session lifecycle ─────────────────────────────────


def compute_client_fingerprint(ip: str, user_agent: str, now: datetime) -> str:
    """Daily-scoped sha256 of ``IP | UA | calendar-day``.

    Rotating per-day caps the blast radius of a single fingerprint and makes
    the daily rate-limit window naturally self-expiring without a cron job.
    """
    day = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return hashlib.sha256(f"{ip}|{user_agent}|{day}".encode("utf-8")).hexdigest()


def get_or_create_session(
    store: Store,
    *,
    opinion: EventOpinion,
    client_fingerprint: str,
    now: Optional[datetime] = None,
) -> FollowUpSession:
    """Look up (or create) a follow-up session anchored to an opinion.

    The id is deterministic on ``(opinion_id, fingerprint, day)`` so the
    same user reading the same opinion on the same day always lands on the
    same session.
    """
    now = now or datetime.now(timezone.utc)
    day_iso = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    sid = make_followup_session_id(opinion.id, client_fingerprint, day_iso)
    existing = store.get_followup_session(sid)
    if existing:
        return existing
    sess = FollowUpSession(
        id=sid,
        opinion_id=opinion.id,
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=24),
        client_fingerprint=client_fingerprint,
        message_count=0,
    )
    store.add_followup_session(sess)
    return sess


# ── rate limits ─────────────────────────────────────────────────────


def _check_rate_limits(store: Store, sess: FollowUpSession, now: datetime) -> None:
    """Raise ``RateLimitExceeded`` before any write if the caller is over cap."""
    msgs = store.list_followup_messages(sess.id)
    user_count = sum(1 for m in msgs if m.role == FollowUpMessageRole.USER)
    if user_count >= RATE_LIMIT_PER_SESSION:
        raise RateLimitExceeded("session_message_cap")
    # The store's ``count_followup_messages_in_window`` counts ALL roles in
    # the window (user + assistant). Each user turn produces one user message
    # and at most one assistant message, so dividing by 2 (rounding up) is a
    # conservative upper bound on the user-message count.
    total = store.count_followup_messages_in_window(
        sess.client_fingerprint, since=now - timedelta(hours=24)
    )
    daily_user = (total + 1) // 2 if total > 0 else 0
    if daily_user >= RATE_LIMIT_PER_FINGERPRINT_PER_DAY:
        raise RateLimitExceeded("daily_cap")


# ── prompt-injection defense / prior-turn formatting ────────────────


def _sanitize_question(text: str) -> str:
    """Run the shared ``PromptSeparator`` over the user question, truncate.

    Behavior matches the opinion generator's ``_sanitize_raw_text`` pattern:
    prefer founder_text when present, else fall back to raw. A single-
    sentence question will often be classified entirely as "prompt-ish"
    content with no founder_sections — we do not want to feed the LLM an
    empty question, so the raw text is the fallback.
    """
    if not text:
        return ""
    try:
        separated = PromptSeparator().separate(text, source_type="written")
        cleaned = separated.founder_text if separated.founder_sections else text
    except Exception as e:  # noqa: BLE001
        logger.warning("followup_prompt_separator_failed", error=str(e))
        cleaned = text
    cleaned = cleaned.strip()
    if len(cleaned) > _MAX_QUESTION_CHARS:
        cleaned = cleaned[:_MAX_QUESTION_CHARS].rstrip() + "\u2026"
    return cleaned


def _format_prior_turns(
    store: Store,
    session_id: str,
    *,
    limit: int = _MAX_PRIOR_TURNS,
    char_cap: int = _MAX_PRIOR_TURN_CHARS,
) -> str:
    """Render the most recent ``limit`` prior turns as a plain-text block."""
    msgs = store.list_followup_messages(session_id)
    if not msgs:
        return "(no prior turns)"
    tail = msgs[-limit:]
    lines: list[str] = []
    for m in tail:
        role = "USER" if m.role == FollowUpMessageRole.USER else "ASSISTANT"
        content = (m.content or "").strip()
        if len(content) > char_cap:
            content = content[:char_cap].rstrip() + "\u2026"
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior turns)"


# ── citation parsing / validation ───────────────────────────────────


def _norm_ws(s: str) -> str:
    return _WS_RE.sub(" ", (s or "").strip()).casefold()


def _full_source_text(
    store: Store,
    *,
    source_kind: str,
    source_id: str,
    fallback: str,
) -> str:
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
        logger.info(
            "followup_citation_full_text_unavailable",
            source_kind=source_kind,
            source_id=source_id,
            error=str(e),
        )
        return fallback
    logger.info(
        "followup_citation_full_text_unavailable",
        source_kind=source_kind,
        source_id=source_id,
    )
    return fallback


def _parse_citations(
    full_text: str,
    hits: list[EventRetrievalHit],
    store: Store,
    *,
    message_id: str,
    opinion_id: str,
) -> tuple[str, list[OpinionCitation]]:
    """Parse + validate trailing ``[[CITE: ...]]`` tags.

    Returns ``(cleaned_text, validated_citations)``. ``cleaned_text`` has all
    CITE tags stripped regardless of validity. Invalid citations (hallucinated
    source id, kind mismatch, or quote that doesn't appear verbatim in the
    stored source body) are discarded with an INFO log — LLMs hallucinate
    regularly, so this is not a warning-level event.
    """
    hit_index: dict[str, EventRetrievalHit] = {h.source_id: h for h in hits}
    citations: list[OpinionCitation] = []
    ordinal = 0
    for m in _CITE_RE.finditer(full_text or ""):
        kind = (m.group("kind") or "").strip()
        sid = (m.group("sid") or "").strip()
        quoted = (m.group("q") or "").strip()
        if kind not in {"conclusion", "claim"}:
            logger.info("followup_bad_citation", reason="bad_kind", kind=kind)
            continue
        hit = hit_index.get(sid)
        if hit is None:
            logger.info(
                "followup_bad_citation",
                reason="hallucinated_source_id",
                source_id=sid,
            )
            continue
        if hit.source_kind != kind:
            logger.info(
                "followup_bad_citation",
                reason="kind_mismatch",
                expected=hit.source_kind,
                got=kind,
            )
            continue
        if not (8 <= len(quoted) <= 240):
            logger.info(
                "followup_bad_citation",
                reason="quote_length_out_of_range",
                length=len(quoted),
            )
            continue
        full = _full_source_text(
            store, source_kind=kind, source_id=sid, fallback=hit.text
        )
        if _norm_ws(quoted) not in _norm_ws(full):
            logger.info(
                "followup_bad_citation",
                reason="quote_not_verbatim",
                source_id=sid,
            )
            continue
        conclusion_id = sid if kind == "conclusion" else None
        claim_id = sid if kind == "claim" else None
        citations.append(
            OpinionCitation(
                id=make_followup_citation_id(message_id, ordinal),
                opinion_id=opinion_id,
                conclusion_id=conclusion_id,
                claim_id=claim_id,
                quoted_span=quoted,
                relevance_score=float(hit.score),
                ordinal=ordinal,
            )
        )
        ordinal += 1

    cleaned = _CITE_RE.sub("", full_text or "").strip()
    return cleaned, citations


# ── refusal helper ──────────────────────────────────────────────────


async def _refuse(
    store: Store,
    session: FollowUpSession,
    *,
    reason: str,
    text: str,
    now: datetime,
    assistant_ordinal: int,
) -> AsyncIterator[FollowUpAnswerChunk]:
    """Persist an assistant refusal message and yield its chunks."""
    msg_id = make_followup_message_id(session.id, assistant_ordinal)
    msg = FollowUpMessage(
        id=msg_id,
        session_id=session.id,
        role=FollowUpMessageRole.ASSISTANT,
        created_at=now,
        content=text,
        citations=[],
        tokens_prompt=0,
        tokens_completion=0,
        refused=True,
        refusal_reason=reason,
    )
    store.add_followup_message(msg)
    store.touch_followup_session(session.id, now=now)
    logger.info(
        "followup_refused",
        session_id=session.id,
        reason=reason,
    )
    yield FollowUpAnswerChunk(text=text, done=False)
    yield FollowUpAnswerChunk(
        text="",
        done=True,
        citations=[],
        refused=True,
        refusal_reason=reason,
    )


# ── main orchestrator ───────────────────────────────────────────────


async def answer_followup(
    store: Store,
    *,
    session: FollowUpSession,
    event: CurrentEvent,
    opinion: EventOpinion,
    user_question: str,
    budget: HourlyBudgetGuard,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    now: Optional[datetime] = None,
) -> AsyncIterator[FollowUpAnswerChunk]:
    """Stream a grounded answer to ``user_question``.

    Flow:
      1. Check rate limits (BEFORE any persistence).
      2. Sanitize + persist the user message.
      3. Fresh ``retrieve_for_event`` — no reuse of the opinion's citations.
         Empty retrieval → refuse with ``no_sources``; LLM never called.
      4. Budget check → on exhaustion refuse with ``budget_exhausted``.
      5. Stream the LLM reply, yielding text deltas as they arrive.
      6. On LLM error mid-stream refuse with ``llm_error:<type>``.
      7. Record budget spend, parse + validate citations, persist assistant
         message, yield final ``done=True`` chunk with validated citations.
    """
    now = now or datetime.now(timezone.utc)

    # 1. Rate limits first — never write before this check.
    _check_rate_limits(store, session, now)

    # 2. Sanitize & persist the user message.
    clean_question = _sanitize_question(user_question)
    # Read a fresh copy of the session to get the current message_count so the
    # ordinal is correct even if the caller passed a stale session object.
    sess_current = store.get_followup_session(session.id) or session
    user_ordinal = sess_current.message_count
    assistant_ordinal = user_ordinal + 1
    user_msg_id = make_followup_message_id(session.id, user_ordinal)
    user_msg = FollowUpMessage(
        id=user_msg_id,
        session_id=session.id,
        role=FollowUpMessageRole.USER,
        created_at=now,
        content=clean_question,
        citations=[],
        tokens_prompt=0,
        tokens_completion=0,
        refused=False,
        refusal_reason=None,
    )
    store.add_followup_message(user_msg)
    store.touch_followup_session(session.id, now=now)

    # 3. Fresh retrieval.
    hits = list(retrieve_for_event(store, event))
    if not hits:
        async for chunk in _refuse(
            store,
            session,
            reason="no_sources",
            text=(
                "I don't have any relevant sources to answer that from the "
                "firm's knowledge base right now."
            ),
            now=now,
            assistant_ordinal=assistant_ordinal,
        ):
            yield chunk
        return

    # Build the user-prompt.
    prior_turns_block = _format_prior_turns(store, session.id)
    sources_block = render_sources_block(hits)
    user_prompt = FOLLOWUP_USER_TEMPLATE.format(
        event_url=event.source_url,
        topic_hint=event.topic_hint or "(none)",
        stance=getattr(opinion.stance, "value", str(opinion.stance)),
        headline=opinion.headline or "(none)",
        prior_turns_block=prior_turns_block,
        sources_block=sources_block,
        question=clean_question,
    )

    # 4. Budget check.
    est_prompt = estimate_tokens(FOLLOWUP_SYSTEM_PROMPT) + estimate_tokens(user_prompt)
    est_completion = DEFAULT_COMPLETION_TOKENS
    if not budget.may_spend(est_prompt, est_completion):
        async for chunk in _refuse(
            store,
            session,
            reason="budget_exhausted",
            text=(
                "The firm's hourly answer budget is exhausted. Please try "
                "again in a few minutes."
            ),
            now=now,
            assistant_ordinal=assistant_ordinal,
        ):
            yield chunk
        return

    # 5. Stream.
    full_text_parts: list[str] = []
    tokens_prompt_total = est_prompt
    tokens_completion_total = 0
    try:
        async for delta in chat_stream_text(
            system=FOLLOWUP_SYSTEM_PROMPT,
            user=user_prompt,
            model=model,
            max_tokens=est_completion,
            api_key=api_key,
        ):
            if not isinstance(delta, LLMStreamChunk):
                # Defensive: tolerate stubs that yield a plain string.
                text_delta = str(delta)
                tokens_prompt_total = est_prompt
                tokens_completion_total = max(
                    tokens_completion_total, estimate_tokens(text_delta)
                )
            else:
                text_delta = delta.text_delta
                tokens_prompt_total = delta.tokens_prompt_so_far
                tokens_completion_total = delta.tokens_completion_so_far
            if text_delta:
                full_text_parts.append(text_delta)
                yield FollowUpAnswerChunk(text=text_delta, done=False)
    except LLMError as e:
        async for chunk in _refuse(
            store,
            session,
            reason=f"llm_error:{type(e).__name__}",
            text=(
                "Sorry — the underlying model is unavailable right now. "
                "Please try again shortly."
            ),
            now=now,
            assistant_ordinal=assistant_ordinal,
        ):
            yield chunk
        return

    # 6. Record budget only on clean completion.
    budget.record(tokens_prompt_total, tokens_completion_total)

    # 7. Parse + validate citations, persist assistant message, final yield.
    assistant_msg_id = make_followup_message_id(session.id, assistant_ordinal)
    raw_answer = "".join(full_text_parts)
    cleaned_text, citations = _parse_citations(
        raw_answer,
        hits,
        store,
        message_id=assistant_msg_id,
        opinion_id=session.opinion_id,
    )
    assistant_msg = FollowUpMessage(
        id=assistant_msg_id,
        session_id=session.id,
        role=FollowUpMessageRole.ASSISTANT,
        created_at=now,
        content=cleaned_text,
        citations=list(citations),
        tokens_prompt=int(tokens_prompt_total),
        tokens_completion=int(tokens_completion_total),
        refused=False,
        refusal_reason=None,
    )
    store.add_followup_message(assistant_msg)
    store.touch_followup_session(session.id, now=now)

    logger.info(
        "followup_answered",
        session_id=session.id,
        sources_considered=len(hits),
        citations_kept=len(citations),
        tokens_prompt=tokens_prompt_total,
        tokens_completion=tokens_completion_total,
    )

    yield FollowUpAnswerChunk(
        text="",
        done=True,
        citations=list(citations),
        refused=False,
        refusal_reason=None,
    )
