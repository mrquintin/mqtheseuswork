"""Select the text Noosphere should analyze from a raw upload.

The Codex deliberately keeps ``Upload.textContent`` as the extracted raw
source. That is useful for auditability, but it is not always the right
input for claim extraction or explorer chunks. A PDF essay, for example,
can contain a writing prompt followed by the actual essay. This module
keeps that distinction explicit: raw text stays raw; analytical text is
the pertinent authorial body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from noosphere.mitigations.prompt_separator import PromptSeparator


_AUDIO_MIME_RE = re.compile(r"^audio/", flags=re.IGNORECASE)
_CONVERSATION_SOURCE_TYPES = {
    "audio",
    "dialectic",
    "podcast",
    "session",
    "transcript",
}


@dataclass(frozen=True)
class PertinentText:
    text: str
    changed: bool
    confidence: float
    founder_sections: int
    prompt_sections: int


def _source_type_is_conversation(source_type: str, mime_type: str) -> bool:
    normalized = (source_type or "").strip().lower()
    return normalized in _CONVERSATION_SOURCE_TYPES or bool(_AUDIO_MIME_RE.match(mime_type or ""))


def select_pertinent_text(
    text: str,
    *,
    source_type: str = "written",
    mime_type: str = "",
    min_retained_chars: int = 120,
) -> PertinentText:
    """Return the text Noosphere should analyze for this upload.

    Conversation-like sources are intentionally left intact: the explorer
    should show the conversation, and conversation geometry needs speaker
    handoffs. Written sources pass through the prompt separator so an
    assignment prompt, interviewer question, or external blockquote does
    not become part of the firm's inferred position.
    """

    raw = (text or "").strip()
    if not raw:
        return PertinentText(
            text="",
            changed=False,
            confidence=1.0,
            founder_sections=0,
            prompt_sections=0,
        )

    if _source_type_is_conversation(source_type, mime_type):
        return PertinentText(
            text=raw,
            changed=False,
            confidence=1.0,
            founder_sections=1,
            prompt_sections=0,
        )

    separated = PromptSeparator().separate(raw, source_type="written")
    founder_text = separated.founder_text.strip()

    should_use_founder_text = (
        bool(separated.prompt_sections)
        and bool(founder_text)
        and len(founder_text) >= min_retained_chars
    )
    if not should_use_founder_text:
        return PertinentText(
            text=raw,
            changed=False,
            confidence=separated.confidence,
            founder_sections=len(separated.founder_sections),
            prompt_sections=len(separated.prompt_sections),
        )

    return PertinentText(
        text=founder_text,
        changed=founder_text != raw,
        confidence=separated.confidence,
        founder_sections=len(separated.founder_sections),
        prompt_sections=len(separated.prompt_sections),
    )
