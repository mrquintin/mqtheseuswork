"""False-positive guardrails for ingestion heuristics."""

from __future__ import annotations

from noosphere.mitigations.ingestion_guard import scan_ingestion_text
from noosphere.mitigations.embedding_text import normalize_for_embedding


def test_benign_methodology_discourse_not_quarantined() -> None:
    text = (
        "We should not ignore edge cases when interpreting instructions from participants, "
        "but that is different from overriding the goals of the session."
    )
    r = scan_ingestion_text(normalize_for_embedding(text), enabled=True)
    assert not r.quarantine
