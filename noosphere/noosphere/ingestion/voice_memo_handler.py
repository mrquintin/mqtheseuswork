"""Voice-memo ingest: transcript → principles, with a tuned prompt.

The Codex front-end captures voice memos via the QuickRecorder
component and routes them through the standard signed-upload path
with ``sourceType="voice_memo"``. By the time this handler runs, the
audio has already been transcribed by the regular audio extractor —
the transcript lives in ``Upload.textContent`` exactly like a typed
note would.

What this module adds on top of the generic ingest path:

1. A ``provenance="voice_memo"`` tag stamped onto every emitted
   ``Conclusion`` so the captures queue (and downstream
   dashboards) can recognise voice-memo-derived principles.

2. A swapped-in *voice-memo* principle prompt
   (``principle_extraction_voice_memo.md``), tuned to the failure
   mode that defeats the base extractor on stream-of-consciousness
   input: the base prompt refuses first-person framing too
   aggressively and discards real rules wrapped in "I keep
   noticing…" / "the way I think about it is…" framings. The voice
   memo prompt instructs the LLM to LIFT THE RULE OUT of the
   wrapper rather than refuse.

The handler is intentionally a thin coordinator on top of the
existing :class:`noosphere.claim_extractor.PrincipleExtractor`. The
extractor's post-processing contract (first-person rejection,
citation drift detection, kind/domain caps) is reused unchanged —
voice memos play by the same final rules, the prompt change just
shifts which spans are SURFACED to the contract for evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from noosphere.claim_extractor import (
    PrincipleExtractor,
    PrincipleRefusal,
    _load_principle_system_prompt,
)
from noosphere.llm import LLMClient
from noosphere.models import (
    Chunk,
    Conclusion,
    ConfidenceTier,
)
from noosphere.observability import get_logger

logger = get_logger(__name__)

PROVENANCE_VOICE_MEMO = "voice_memo"

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "extractors" / "_prompts"
_VOICE_MEMO_PROMPT_PATH = _PROMPTS_DIR / "principle_extraction_voice_memo.md"


def load_voice_memo_principle_prompt() -> str:
    """Return the voice-memo system prompt + base extractor examples.

    We keep using the base extractor's worked examples file so the
    LLM still sees concrete formatting guidance — the voice-memo
    prompt only overrides the *framing* of when to refuse vs. lift.
    Joining the two strings mirrors `_load_principle_system_prompt`
    from the base extractor; if the voice-memo prompt is missing
    (mispackaging, partial check-out) we fall back to the base
    prompt rather than crashing the ingest.
    """

    examples_path = _PROMPTS_DIR / "principle_extraction_examples.md"
    if not _VOICE_MEMO_PROMPT_PATH.exists():
        logger.warning(
            "voice_memo_prompt_missing",
            path=str(_VOICE_MEMO_PROMPT_PATH),
        )
        return _load_principle_system_prompt()
    system = _VOICE_MEMO_PROMPT_PATH.read_text(encoding="utf-8")
    examples = examples_path.read_text(encoding="utf-8") if examples_path.exists() else ""
    if not examples:
        return system
    return f"{system}\n\n---\n\n{examples}"


@dataclass
class VoiceMemoIngestResult:
    """What the founder sees in /captures after one voice memo is ingested."""

    upload_id: str
    chunk_count: int
    conclusions: list[Conclusion] = field(default_factory=list)
    refusals: list[PrincipleRefusal] = field(default_factory=list)
    provenance: str = PROVENANCE_VOICE_MEMO

    def principle_texts(self) -> list[str]:
        return [c.text for c in self.conclusions]


def _split_into_chunks(transcript: str, *, max_chars: int = 1800) -> list[str]:
    """Break a transcript into roughly-paragraph-sized chunks.

    Voice memos arrive as one long blob — Whisper does not insert
    paragraph breaks. We split on sentence boundaries within a
    ``max_chars`` budget so each chunk fits comfortably in the LLM
    context with room for the prompt and the JSON response.
    Crude but stable; the principle extractor copes with rough
    chunk boundaries because the contract is span-citation, not
    chunk-level.
    """

    text = transcript.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(len(text), cursor + max_chars)
        # Walk back to the nearest sentence boundary if there's room.
        if end < len(text):
            window = text[cursor:end]
            for boundary in (". ", "! ", "? ", "\n\n"):
                last = window.rfind(boundary)
                if last > max_chars * 0.4:
                    end = cursor + last + len(boundary)
                    break
        out.append(text[cursor:end].strip())
        cursor = end
    return [c for c in out if c]


def _build_chunks(
    transcript: str,
    *,
    upload_id: str,
    recorded_at_iso: Optional[str],
) -> list[Chunk]:
    """Wrap a transcript into ``Chunk`` rows with voice-memo metadata.

    The metadata dict ends up serialized into the LLM user message
    by `PrincipleExtractor.extract`; tagging
    ``{"provenance": "voice_memo"}`` here is what tells the LLM
    (and any future debugger reading the prompt log) that the
    chunk came from a stream-of-consciousness source.
    """

    chunks: list[Chunk] = []
    body_parts = _split_into_chunks(transcript)
    for idx, body in enumerate(body_parts):
        metadata: dict[str, str] = {
            "provenance": PROVENANCE_VOICE_MEMO,
            "upload_id": upload_id,
            "chunk_index": str(idx),
            "chunk_count": str(len(body_parts)),
        }
        if recorded_at_iso:
            metadata["recorded_at"] = recorded_at_iso
        offset_start = 0 if idx == 0 else sum(len(b) for b in body_parts[:idx])
        offset_end = offset_start + len(body)
        chunks.append(
            Chunk(
                artifact_id=upload_id,
                start_offset=offset_start,
                end_offset=offset_end,
                text=body,
                metadata=metadata,
            )
        )
    return chunks


def _stamp_provenance(conclusion: Conclusion) -> Conclusion:
    """Attach the voice-memo provenance tag to a conclusion.

    Conclusion does not have a dedicated `provenance` column; the
    `rationale` field is the canonical place for free-form
    provenance metadata in this codebase. We prepend a small
    tag line so the captures page (and future filters) can
    recognise voice-memo-derived conclusions without a schema
    change. Existing rationale (the domain-of-applicability the
    extractor wrote) is preserved after the tag.
    """

    tag = f"[provenance={PROVENANCE_VOICE_MEMO}]"
    existing = (conclusion.rationale or "").strip()
    if tag in existing:
        return conclusion
    new_rationale = tag if not existing else f"{tag} {existing}"
    conclusion.rationale = new_rationale
    return conclusion


def ingest_voice_memo_transcript(
    transcript: str,
    *,
    upload_id: str,
    recorded_at_iso: Optional[str] = None,
    llm: Optional[LLMClient] = None,
    confidence_tier: ConfidenceTier = ConfidenceTier.MODERATE,
    principle_extractor_factory: Optional[
        Callable[[LLMClient], PrincipleExtractor]
    ] = None,
) -> VoiceMemoIngestResult:
    """Run the principle extractor against a voice-memo transcript.

    The handler:

    1. Splits the transcript into LLM-sized chunks.
    2. Tags each chunk with ``provenance=voice_memo`` metadata so
       the principle prompt context advertises the source kind.
    3. Builds a :class:`PrincipleExtractor` that uses the voice-memo
       system prompt instead of the base prompt.
    4. Stamps the resulting :class:`Conclusion` rows with
       ``[provenance=voice_memo]`` in their rationale so the queue
       page can recognise them.

    The function is pure-compute — it does NOT touch the database.
    Storage of the conclusions is done by the caller (Codex
    bridge / ingester), which already knows the
    organisation/founder context and the dedup contract.

    ``principle_extractor_factory`` exists for tests so they can
    inject a custom extractor (e.g. one with a recording LLM
    client). Production code passes ``llm=...`` and lets the
    factory default through.
    """

    if not transcript or not transcript.strip():
        return VoiceMemoIngestResult(upload_id=upload_id, chunk_count=0)

    chunks = _build_chunks(
        transcript, upload_id=upload_id, recorded_at_iso=recorded_at_iso
    )
    if not chunks:
        return VoiceMemoIngestResult(upload_id=upload_id, chunk_count=0)

    if principle_extractor_factory is None:
        # Default factory: build a PrincipleExtractor and monkey-patch
        # its prompt-load helper to use the voice-memo system prompt.
        # We do this rather than subclassing so the rest of the
        # extractor's post-processing contract (first-person reject,
        # citation drift, kind/domain caps) stays a single source of
        # truth.
        def _factory(client: LLMClient) -> PrincipleExtractor:
            extractor = PrincipleExtractor(llm=client)
            return _with_voice_memo_prompt(extractor)

        principle_extractor_factory = _factory

    if llm is None:
        # Lazy import to keep voice_memo_handler import cost low for
        # callers that only need `load_voice_memo_principle_prompt`.
        from noosphere.llm import llm_client_from_settings

        llm = llm_client_from_settings()

    extractor = principle_extractor_factory(llm)

    all_conclusions: list[Conclusion] = []
    all_refusals: list[PrincipleRefusal] = []
    for chunk in chunks:
        try:
            conclusions, refusals = extractor.extract(
                chunk,
                episode_id=upload_id,
                confidence_tier=confidence_tier,
            )
        except Exception as exc:
            # One bad chunk should not abort the whole memo — the
            # founder is likely to want SOMETHING out of the capture
            # even if one chunk made the LLM stumble. Log and
            # continue.
            logger.warning(
                "voice_memo_chunk_extract_failed",
                upload_id=upload_id,
                chunk_id=chunk.id,
                error=str(exc),
            )
            continue
        for c in conclusions:
            all_conclusions.append(_stamp_provenance(c))
        all_refusals.extend(refusals)

    return VoiceMemoIngestResult(
        upload_id=upload_id,
        chunk_count=len(chunks),
        conclusions=all_conclusions,
        refusals=all_refusals,
    )


def _with_voice_memo_prompt(
    extractor: PrincipleExtractor,
) -> PrincipleExtractor:
    """Patch ``extractor`` to use the voice-memo system prompt.

    The base extractor calls a module-level ``_load_principle_system_prompt``
    inside ``extract``. We can't override that without subclassing,
    so we patch the extract method to splice in the voice-memo
    prompt at call time. This keeps the change local to the voice-
    memo handler and leaves the base extractor untouched.
    """

    voice_memo_prompt = load_voice_memo_principle_prompt()
    original_extract = extractor.extract

    def patched_extract(
        chunk: Chunk,
        *,
        episode_id: str = "ingest",
        episode_date: Any = None,
        confidence_tier: ConfidenceTier = ConfidenceTier.MODERATE,
    ) -> tuple[list[Conclusion], list[PrincipleRefusal]]:
        # Temporarily redirect the prompt loader for the duration of
        # this call. We do this by replacing the module-level helper
        # on the claim_extractor module — the extractor reads through
        # it on each call. Restore on the way out, even on failure,
        # so concurrent non-voice-memo extracts are unaffected.
        import noosphere.claim_extractor as ce_mod

        previous_loader = ce_mod._load_principle_system_prompt
        ce_mod._load_principle_system_prompt = lambda: voice_memo_prompt
        try:
            return original_extract(
                chunk,
                episode_id=episode_id,
                episode_date=episode_date,
                confidence_tier=confidence_tier,
            )
        finally:
            ce_mod._load_principle_system_prompt = previous_loader

    extractor.extract = patched_extract  # type: ignore[method-assign]
    return extractor
