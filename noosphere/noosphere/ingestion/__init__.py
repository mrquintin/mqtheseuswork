"""Noosphere ingestion-side helpers for upload-shaped artifacts.

The voice-memo handler lives here; other ingestion-shaped helpers
(PDF ingest, transcript ingest) live in their own modules. The
package is intentionally light — most ingestion logic lives in
:mod:`noosphere.codex_bridge` and :mod:`noosphere.ingester`. This
package collects the *artifact-type-specific* glue: code that knows
"a voice memo is a stream-of-consciousness transcript and the
principle extractor needs the relaxed prompt for it" goes here.
"""

from noosphere.ingestion.voice_memo_handler import (
    PROVENANCE_VOICE_MEMO,
    VoiceMemoIngestResult,
    ingest_voice_memo_transcript,
    load_voice_memo_principle_prompt,
)

__all__ = [
    "PROVENANCE_VOICE_MEMO",
    "VoiceMemoIngestResult",
    "ingest_voice_memo_transcript",
    "load_voice_memo_principle_prompt",
]
