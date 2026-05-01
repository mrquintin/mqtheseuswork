"""Bridge generated Currents opinions into held social-post drafts."""

from __future__ import annotations

from typing import Any

from noosphere.models import SocialPost
from noosphere.social.x_formatter import format_for_x_async, weighted_x_length

SOURCE_CURRENTS_OPINION = "currents.opinion"


async def create_x_draft_for_event_opinion(
    store: Any,
    event_id: str,
    *,
    llm_client: Any | None = None,
) -> str | None:
    opinion = store.latest_event_opinion_for_event(event_id)
    if opinion is None:
        return None

    existing = store.find_social_post_by_source(
        platform="x",
        source=SOURCE_CURRENTS_OPINION,
        source_id=opinion.id,
    )
    if existing is not None:
        return existing.id

    event = store.get_current_event(event_id)
    source_url = str(getattr(event, "url", "") or "")
    if not source_url.startswith("https://"):
        return _record_rejected(
            store,
            organization_id=opinion.organization_id,
            opinion_id=opinion.id,
            reason="source event has no https URL",
        )

    payload = await format_for_x_async(opinion, source_url, llm_client=llm_client)
    if payload is None:
        body = _body_preview(opinion)
        return _record_rejected(
            store,
            organization_id=opinion.organization_id,
            opinion_id=opinion.id,
            reason=(
                "formatter could not produce a <=280 weighted-char post "
                f"(preview_weighted_length={weighted_x_length(body)})"
            ),
            body=body,
        )

    post = SocialPost(
        organization_id=opinion.organization_id,
        source=SOURCE_CURRENTS_OPINION,
        source_id=opinion.id,
        platform="x",
        body=payload["body"],
        media=[],
        status="draft",
    )
    return store.add_social_post(post)


def _record_rejected(
    store: Any,
    *,
    organization_id: str,
    opinion_id: str,
    reason: str,
    body: str = "",
) -> str:
    post = SocialPost(
        organization_id=organization_id,
        source=SOURCE_CURRENTS_OPINION,
        source_id=opinion_id,
        platform="x",
        body=body,
        media=[],
        status="rejected",
        failure_reason=reason,
    )
    return store.add_social_post(post)


def _body_preview(opinion: Any) -> str:
    return str(getattr(opinion, "body_markdown", "") or "")[:512]
