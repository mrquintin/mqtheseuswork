"""Noosphere ingestion-side helpers for upload-shaped artifacts.

The voice-memo handler lives here; other ingestion-shaped helpers
(PDF ingest, transcript ingest) live in their own modules. The
package is intentionally light — most ingestion logic lives in
:mod:`noosphere.codex_bridge` and :mod:`noosphere.ingester`. This
package collects the *artifact-type-specific* glue: code that knows
"a voice memo is a stream-of-consciousness transcript and the
principle extractor needs the relaxed prompt for it" goes here.

Also re-exports :class:`ProvenanceKind` and the
:func:`apply_upload_provenance` helper — every upload path eventually
goes through ingestion, and the founder's upload-time tag must be
stamped onto the :class:`Artifact` row before it's persisted.
Provenance is set at UPLOAD TIME and is **never** inferred from
content (prompt 09).
"""

from __future__ import annotations

from typing import Optional

from noosphere.ingestion.voice_memo_handler import (
    PROVENANCE_VOICE_MEMO,
    VoiceMemoIngestResult,
    ingest_voice_memo_transcript,
    load_voice_memo_principle_prompt,
)
from noosphere.models import (
    EXTERNAL_PROVENANCE_KINDS,
    PROVENANCE_KIND_VALUES,
    PROVENANCE_RATIONALE_MIN_LEN,
    Artifact,
    ProvenanceKind,
    coerce_provenance,
    validate_provenance_rationale,
)


def apply_upload_provenance(
    artifact: Artifact,
    *,
    provenance: ProvenanceKind | str | None,
    rationale: str | None,
) -> Artifact:
    """Stamp the founder's upload-time choice onto an :class:`Artifact`.

    Called by every upload path (UI, CLI, codex bridge) right before
    ``store.put_artifact``. Refuses external provenance without a
    ≥30-character rationale and refuses unknown kinds outright.

    The agent must NEVER call this with an inferred value — only with
    what the founder explicitly selected via the upload UI / CLI.
    Misuse is a bug, not a recoverable state.
    """

    if provenance is None:
        kind = ProvenanceKind.PROPRIETARY
    else:
        # ProvenanceKind() raises ValueError on unknown strings — this is
        # the right behaviour: we want a hard fail when the upload form
        # is wired to a kind we don't recognise.
        if isinstance(provenance, ProvenanceKind):
            kind = provenance
        else:
            kind = ProvenanceKind(str(provenance).upper())
    rationale_clean = validate_provenance_rationale(kind, rationale)
    artifact.provenance = kind
    artifact.provenance_rationale = rationale_clean
    return artifact


__all__ = [
    "PROVENANCE_KIND_VALUES",
    "PROVENANCE_RATIONALE_MIN_LEN",
    "PROVENANCE_VOICE_MEMO",
    "EXTERNAL_PROVENANCE_KINDS",
    "ProvenanceKind",
    "VoiceMemoIngestResult",
    "apply_upload_provenance",
    "coerce_provenance",
    "ingest_voice_memo_transcript",
    "load_voice_memo_principle_prompt",
    "validate_provenance_rationale",
]
