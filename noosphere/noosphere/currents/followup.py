"""Public follow-up answering with fresh retrieval and citation filtering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from sqlalchemy import desc
from sqlmodel import select

from noosphere.currents._llm_client import LLMResponse, make_client
from noosphere.currents.opinion_generator import (
    DEFAULT_TOP_K,
    _estimate_tokens,
    _extract_json_object,
    _source_blocks,
    validate_citations,
)
from noosphere.mitigations.prompt_separator import PromptSeparator
from noosphere.models import FollowUpMessage, FollowUpRole, FollowUpSession


RATE_LIMIT_PER_FINGERPRINT_PER_DAY = 20
RATE_LIMIT_PER_SESSION = 8
MIN_INTERVAL_BETWEEN_MESSAGES_SECONDS = 2
FOLLOWUP_MAX_TOKENS = 1_000
PROMPT_SEPARATOR_BEGIN = "<<<PROMPT_SEPARATOR_UNTRUSTED_USER_QUESTION_BEGIN>>>"
PROMPT_SEPARATOR_END = "<<<PROMPT_SEPARATOR_UNTRUSTED_USER_QUESTION_END>>>"


@dataclass
class FollowupAnswerChunk:
    kind: Literal["meta", "token", "citation", "done"]
    text: str | None
    citation: dict | None


class FollowupRateLimited(Exception):
    """429-style error for the FastAPI layer to translate."""

    def __init__(self, reason: str, *, retry_after_s: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = 429
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class _QuestionEvent:
    id: str
    text: str
    topic_hint: str | None = None
    embedding: bytes | None = None


def retrieve_for_event(store: Any, event: Any, top_k: int = DEFAULT_TOP_K) -> list[Any]:
    """Lazy wrapper so mocked follow-up tests do not import NumPy eagerly."""
    from noosphere.currents.retrieval_adapter import retrieve_for_event as _retrieve_for_event

    return _retrieve_for_event(store, event, top_k=top_k)


def _prompt_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "_prompts" / name


def _read_system_prompt(name: str) -> str:
    return _prompt_path(name).read_text(encoding="utf-8").strip()


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _day_bounds_utc(now: datetime) -> tuple[datetime, datetime]:
    start = datetime(now.year, now.month, now.day)
    return start, start + timedelta(days=1)


def _user_message_count_for_session(store: Any, session_id: str) -> int:
    with store.session() as db:
        rows = db.exec(
            select(FollowUpMessage)
            .where(FollowUpMessage.session_id == session_id)
            .where(FollowUpMessage.role == FollowUpRole.USER)
        ).all()
        return len(rows)


def _last_user_message_for_session(store: Any, session_id: str) -> FollowUpMessage | None:
    with store.session() as db:
        return db.exec(
            select(FollowUpMessage)
            .where(FollowUpMessage.session_id == session_id)
            .where(FollowUpMessage.role == FollowUpRole.USER)
            .order_by(desc(FollowUpMessage.created_at))
        ).first()


def _fingerprint_user_count_today(store: Any, fingerprint: str, now: datetime) -> int:
    day_start, day_end = _day_bounds_utc(now)
    with store.session() as db:
        rows = db.exec(
            select(FollowUpMessage)
            .join(FollowUpSession, FollowUpMessage.session_id == FollowUpSession.id)
            .where(FollowUpSession.client_fingerprint == fingerprint)
            .where(FollowUpMessage.role == FollowUpRole.USER)
            .where(FollowUpMessage.created_at >= day_start)
            .where(FollowUpMessage.created_at < day_end)
        ).all()
        return len(rows)


def _enforce_rate_limits(store: Any, session: FollowUpSession, now: datetime) -> None:
    fingerprint_count = _fingerprint_user_count_today(
        store,
        session.client_fingerprint,
        now,
    )
    if fingerprint_count >= RATE_LIMIT_PER_FINGERPRINT_PER_DAY:
        raise FollowupRateLimited("fingerprint_daily_limit")

    session_count = _user_message_count_for_session(store, session.id)
    if session_count >= RATE_LIMIT_PER_SESSION:
        raise FollowupRateLimited("session_message_limit")

    last_user_message = _last_user_message_for_session(store, session.id)
    if last_user_message is not None:
        elapsed = (now - last_user_message.created_at).total_seconds()
        if elapsed < MIN_INTERVAL_BETWEEN_MESSAGES_SECONDS:
            retry_after = max(1, int(MIN_INTERVAL_BETWEEN_MESSAGES_SECONDS - elapsed))
            raise FollowupRateLimited("min_interval", retry_after_s=retry_after)


def _wrap_question(user_question: str) -> str:
    PromptSeparator().separate(user_question, source_type="written")
    return "\n".join(
        [
            PROMPT_SEPARATOR_BEGIN,
            user_question,
            PROMPT_SEPARATOR_END,
        ]
    )


def _followup_prompt(
    *,
    opinion: Any,
    session_id: str,
    wrapped_question: str,
    hits: list[Any],
) -> str:
    return "\n\n".join(
        [
            "EXISTING OPINION CONTEXT",
            f"opinion_id: {getattr(opinion, 'id', '')}",
            f"session_id: {session_id}",
            f"headline: {getattr(opinion, 'headline', '')}",
            "body_markdown:",
            getattr(opinion, "body_markdown", ""),
            "FRESHLY RETRIEVED THESEUS SOURCES",
            _source_blocks(hits),
            "UNTRUSTED USER QUESTION",
            wrapped_question,
            "Return the strict JSON object specified by the system prompt.",
        ]
    )


async def _call_followup_llm(
    client: Any,
    *,
    system: str,
    user: str,
) -> LLMResponse:
    stream = getattr(client, "stream", None)
    if callable(stream):
        parts: list[str] = []
        prompt_tokens = 0
        completion_tokens = 0
        model = ""
        async for chunk in stream(
            system=system,
            user=user,
            max_tokens=FOLLOWUP_MAX_TOKENS,
            temperature=0.0,
        ):
            if getattr(chunk, "kind", None) == "token" and getattr(chunk, "text", None):
                parts.append(chunk.text)
            elif getattr(chunk, "kind", None) == "done":
                prompt_tokens = int(getattr(chunk, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(chunk, "completion_tokens", 0) or 0)
                model = str(getattr(chunk, "model", "") or "")
        return LLMResponse(
            text="".join(parts),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
        )

    return await client.complete(
        system=system,
        user=user,
        max_tokens=FOLLOWUP_MAX_TOKENS,
        temperature=0.0,
    )


def _parse_followup_response(raw_text: str) -> tuple[str, Any]:
    try:
        payload = _extract_json_object(raw_text)
    except (json.JSONDecodeError, ValueError):
        return (
            "I cannot answer that with validated retrieved sources.",
            [],
        )
    answer = str(payload.get("answer_markdown") or "").strip()
    if not answer:
        answer = "I cannot answer that with validated retrieved sources."
    return answer, payload.get("citations", [])


def _text_chunks(text: str, *, size: int = 96) -> list[str]:
    if not text:
        return []
    return [text[idx : idx + size] for idx in range(0, len(text), size)]


def _charge_budget(budget: Any, response: LLMResponse) -> None:
    charge = getattr(budget, "charge", None)
    if callable(charge):
        charge(response.prompt_tokens, response.completion_tokens)


def _authorize_budget(budget: Any, *, system: str, user: str) -> None:
    authorize = getattr(budget, "authorize", None)
    if callable(authorize):
        authorize(_estimate_tokens(system, user), FOLLOWUP_MAX_TOKENS)


async def answer_followup(
    store: Any,
    opinion_id: str,
    session_id: str,
    user_question: str,
    *,
    budget: Any,
) -> AsyncIterator[FollowupAnswerChunk]:
    """
    Re-retrieve for the question, wrap untrusted input, answer with Haiku,
    drop invalid citations, persist the exchange, and yield response chunks.
    """
    opinion = store.get_event_opinion(opinion_id)
    if opinion is None:
        raise KeyError(f"unknown opinion: {opinion_id}")
    session = store.get_followup_session(session_id)
    if session is None:
        raise KeyError(f"unknown follow-up session: {session_id}")
    if session.opinion_id != opinion_id:
        raise ValueError("follow-up session does not belong to opinion")

    now = _utcnow_naive()
    _enforce_rate_limits(store, session, now)

    question_event = _QuestionEvent(id=f"followup:{session_id}", text=user_question)
    hits = retrieve_for_event(store, question_event, top_k=DEFAULT_TOP_K)
    wrapped_question = _wrap_question(user_question)
    system_prompt = _read_system_prompt("followup_system.md")
    user_prompt = _followup_prompt(
        opinion=opinion,
        session_id=session_id,
        wrapped_question=wrapped_question,
        hits=hits,
    )
    _authorize_budget(budget, system=system_prompt, user=user_prompt)

    client = make_client()
    response = await _call_followup_llm(client, system=system_prompt, user=user_prompt)
    _charge_budget(budget, response)
    answer_text, raw_citations = _parse_followup_response(response.text)
    citations, _errors = validate_citations(raw_citations, hits, require_any=False)

    store.add_followup_message(
        FollowUpMessage(
            session_id=session_id,
            role=FollowUpRole.USER,
            content=user_question,
            created_at=now,
        )
    )
    store.add_followup_message(
        FollowUpMessage(
            session_id=session_id,
            role=FollowUpRole.ASSISTANT,
            content=answer_text,
            citations=citations,
            created_at=_utcnow_naive(),
        )
    )

    meta = {
        "opinion_id": opinion_id,
        "session_id": session_id,
        "model": response.model,
        "source_count": len(hits),
    }
    yield FollowupAnswerChunk(kind="meta", text=json.dumps(meta, sort_keys=True), citation=None)
    for chunk in _text_chunks(answer_text):
        yield FollowupAnswerChunk(kind="token", text=chunk, citation=None)
    for citation in citations:
        yield FollowupAnswerChunk(kind="citation", text=None, citation=citation)
    yield FollowupAnswerChunk(kind="done", text=None, citation=None)
