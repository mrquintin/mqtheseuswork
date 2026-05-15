"""Voice-memo ingest contract.

The QuickRecorder front-end uploads voice memos through the standard
artifact-upload path with ``sourceType="voice_memo"``. Audio is
transcribed by the existing audio extractor; the resulting transcript
is then handed to :func:`ingest_voice_memo_transcript`, which:

  1. uses the voice-memo-specific principle extraction prompt
     (``principle_extraction_voice_memo.md``);
  2. stamps every emitted Conclusion's rationale with
     ``[provenance=voice_memo]`` so the captures queue can filter;
  3. surfaces refusals from the underlying PrincipleExtractor unchanged
     (the contract that rejects first-person framings still applies).

These tests pin those guarantees with a mocked LLM. The audio
transcription step itself is exercised in
``noosphere/tests/test_extractors_audio.py`` — here we start FROM the
transcript and care about the principle-extraction half of the
pipeline.
"""

from __future__ import annotations

import json

import pytest

from noosphere.ingestion.voice_memo_handler import (
    PROVENANCE_VOICE_MEMO,
    VoiceMemoIngestResult,
    ingest_voice_memo_transcript,
    load_voice_memo_principle_prompt,
)
from noosphere.llm import MockLLMClient
from noosphere.models import ConfidenceTier


# ── helpers ────────────────────────────────────────────────────────────────


def _principle_payload(text: str, source_span: str, kind: str = "RULE") -> dict:
    return {
        "text": text,
        "source_span": source_span,
        "principle_kind": kind,
        "domain_of_applicability": "voice-memo test domain",
        "quantifiable_proxies": ["throughput_per_artifact"],
        "decision_examples": ["choose unified ingest over ad hoc"],
    }


def _scripted_llm(payloads: list[dict]) -> MockLLMClient:
    """One scripted JSON response per chunk the handler will produce."""

    return MockLLMClient(responses=[json.dumps(p) for p in payloads])


# ── prompt loader sanity ────────────────────────────────────────────────────


def test_voice_memo_prompt_loads_with_examples() -> None:
    text = load_voice_memo_principle_prompt()
    # Voice-memo specific framing must be present (vs. the base prompt
    # which refuses on first-person framings rather than lifting).
    assert "voice memo" in text.lower()
    assert "stream-of-consciousness" in text.lower() or "stream of consciousness" in text.lower()
    # Base-prompt examples are spliced in so the LLM still sees
    # concrete shape guidance.
    assert "principle_kind" in text
    assert "source_span" in text


# ── happy path: stream-of-consciousness → principle, with provenance ────────


def test_voice_memo_ingest_lifts_principle_from_first_person_wrapper() -> None:
    # A canonical founder voice-memo span. The base prompt would
    # refuse this as autobiographical framing; the voice-memo prompt
    # lifts the rule out. We assert the post-processing contract
    # accepts the resulting principle and stamps provenance.
    transcript = (
        "Long as we're recording something, long as we're collecting "
        "data of some kind, we can feed it through some ingestion "
        "pipeline to automate and refine processes."
    )
    extracted_span = (
        "we can feed it through some ingestion "
        "pipeline to automate and refine processes"
    )
    llm = _scripted_llm(
        [
            {
                "principles": [
                    _principle_payload(
                        "Any recorded artifact a firm captures should pass through a single ingestion pipeline.",
                        extracted_span,
                        kind="RULE",
                    )
                ],
                "refusals": [],
            }
        ]
    )

    result = ingest_voice_memo_transcript(
        transcript,
        upload_id="upl_test_001",
        recorded_at_iso="2026-05-15T10:00:00Z",
        llm=llm,
    )

    assert isinstance(result, VoiceMemoIngestResult)
    assert result.upload_id == "upl_test_001"
    assert result.chunk_count == 1
    assert result.provenance == PROVENANCE_VOICE_MEMO
    assert len(result.conclusions) == 1
    assert len(result.refusals) == 0

    conclusion = result.conclusions[0]
    # Provenance tag stamped into rationale so the captures page can
    # filter without a schema change.
    assert f"[provenance={PROVENANCE_VOICE_MEMO}]" in (conclusion.rationale or "")
    # Third-person contract still enforced — no "I"/"we"/"my"/"our".
    assert not conclusion.text.lower().lstrip().startswith(("i ", "we ", "my ", "our "))
    # Source span citation preserved verbatim so the queue can
    # highlight it in the transcript.
    assert conclusion.source_span == extracted_span

    # Voice-memo prompt was actually sent to the LLM (not the base
    # prompt). The voice-memo system prompt mentions
    # "stream-of-consciousness" explicitly.
    sent_system = llm.calls[0]["system"].lower()
    assert "stream-of-consciousness" in sent_system or "stream of consciousness" in sent_system
    # And the chunk metadata advertises voice-memo provenance to the
    # LLM in the user message, so any future LLM behaviour can branch
    # on it.
    assert PROVENANCE_VOICE_MEMO in llm.calls[0]["user"]


# ── refusal path: pure autobiography stays refused ──────────────────────────


def test_voice_memo_ingest_passes_through_refusals() -> None:
    transcript = (
        "I, uh, I'm just thinking out loud here. This week's been weird. "
        "I should probably make dinner."
    )
    llm = _scripted_llm(
        [
            {
                "principles": [],
                "refusals": [
                    {
                        "refusal": "NO_PRINCIPLE_EXTRACTABLE",
                        "source_span": transcript,
                        "reason": "Autobiographical small talk; no transferable rule.",
                    }
                ],
            }
        ]
    )

    result = ingest_voice_memo_transcript(
        transcript,
        upload_id="upl_test_002",
        llm=llm,
    )
    assert len(result.conclusions) == 0
    assert len(result.refusals) == 1
    assert result.refusals[0].refusal == "NO_PRINCIPLE_EXTRACTABLE"


# ── empty transcript edge case ─────────────────────────────────────────────


def test_voice_memo_ingest_empty_transcript_returns_empty_result() -> None:
    llm = MockLLMClient(responses=[])
    result = ingest_voice_memo_transcript("", upload_id="upl_empty", llm=llm)
    assert result.upload_id == "upl_empty"
    assert result.chunk_count == 0
    assert result.conclusions == []
    assert result.refusals == []
    # Importantly, no LLM call was made — empty input must not burn
    # tokens.
    assert llm.calls == []


# ── first-person guard still rejects the LLM trying to slip one in ─────────


def test_voice_memo_ingest_still_rejects_first_person_text_from_llm() -> None:
    transcript = "When a thesis cannot be falsified in 18 months it is not a thesis."
    # LLM returns a forbidden first-person text. The post-processing
    # contract on the base PrincipleExtractor must demote it to a
    # refusal — even though we are using the voice-memo prompt.
    llm = _scripted_llm(
        [
            {
                "principles": [
                    _principle_payload(
                        "I think a thesis must be falsifiable in 18 months.",
                        transcript,
                        kind="CRITERION",
                    )
                ],
                "refusals": [],
            }
        ]
    )
    result = ingest_voice_memo_transcript(
        transcript,
        upload_id="upl_first_person",
        llm=llm,
    )
    assert result.conclusions == []
    assert len(result.refusals) == 1


# ── discard semantics: no server-side artifact on a discarded capture ──────


def test_voice_memo_discard_leaves_no_server_artifact() -> None:
    """A discarded recording must NEVER reach the ingest path.

    The Codex front-end's `AudioRecorder.discard()` releases the mic
    and drops the blob in-browser before any upload begins. From the
    Python side this means `ingest_voice_memo_transcript` is simply
    never invoked. We pin that contract here by asserting that
    *not calling* the function leaves no Conclusion-shaped state:
    constructing a `VoiceMemoIngestResult` for a never-uploaded
    capture is impossible from this module's public API.
    """

    # The only way to mint a result is by passing a transcript. A
    # discarded recording has no transcript and no upload_id — the
    # ingest entry point is never reached, so no module-level
    # registry / queue / cache exists to be cleaned up.
    import noosphere.ingestion.voice_memo_handler as handler

    public_names = [n for n in dir(handler) if not n.startswith("_")]
    # No module-level singletons that could carry residue from a
    # discarded capture.
    for name in public_names:
        attr = getattr(handler, name)
        if callable(attr):
            continue
        # Module-level constants are fine; mutable shared state would
        # be a bug because a discarded recording could otherwise
        # leak into a later session.
        assert not isinstance(attr, (list, dict, set)), (
            f"voice_memo_handler.{name} is mutable module-level state; "
            "discarded captures could leave residue here."
        )


# ── multi-chunk transcripts get sent through the same prompt ──────────────


def test_voice_memo_long_transcript_is_chunked_and_each_chunk_uses_voice_prompt() -> None:
    # Build a transcript long enough to trigger the chunker (max
    # default ~1800 chars). Each chunk should receive the voice-memo
    # prompt independently — not the base prompt.
    paragraph = (
        "When teams ship faster than they can write postmortems, "
        "the quality of postmortems degrades to the point that "
        "they no longer teach anything. " * 8
    )
    transcript = (paragraph + " ") * 4  # ~ several thousand chars
    # Script the LLM to emit no-op responses for each chunk; we only
    # care that the call count and the prompt match the contract.
    llm = MockLLMClient(
        responses=[json.dumps({"principles": [], "refusals": []})] * 10
    )

    result = ingest_voice_memo_transcript(
        transcript,
        upload_id="upl_long_001",
        llm=llm,
    )
    assert result.chunk_count >= 2
    assert len(llm.calls) == result.chunk_count
    for call in llm.calls:
        sys_lower = call["system"].lower()
        assert "stream-of-consciousness" in sys_lower or "stream of consciousness" in sys_lower


# ── confidence tier override is honoured ────────────────────────────────────


def test_voice_memo_confidence_tier_override() -> None:
    transcript = "A founder who cannot state the strongest counter-argument has not stress-tested the thesis."
    llm = _scripted_llm(
        [
            {
                "principles": [
                    _principle_payload(
                        "A founder must be able to state the strongest counter-argument before a thesis can be considered stress-tested.",
                        transcript,
                        kind="CRITERION",
                    )
                ],
                "refusals": [],
            }
        ]
    )
    result = ingest_voice_memo_transcript(
        transcript,
        upload_id="upl_tier",
        llm=llm,
        confidence_tier=ConfidenceTier.LOW,
    )
    assert len(result.conclusions) == 1
    assert result.conclusions[0].confidence_tier == ConfidenceTier.LOW
