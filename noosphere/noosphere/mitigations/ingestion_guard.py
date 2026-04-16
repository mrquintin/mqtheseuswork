"""
Heuristic prompt-injection / instruction-override detection for ingested text.

This is not a substitute for a fine-tuned classifier; it is a cheap first line
that flags obvious jailbreak tropes for quarantine + human review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from noosphere.config import get_settings
from noosphere.models import Claim
from noosphere.mitigations.embedding_text import normalize_for_embedding, zero_width_count

# Tuned for recall on known patterns; benign corpus review in tests.
_INJECTION_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+previous\s+instructions", re.I),
    re.compile(r"disregard\s+(the\s+)?(above|prior)", re.I),
    re.compile(
        r"you\s+are\s+now\s+(?:a|an)?\s*(?:chatgpt|gpt-\d|assistant|developer\s+mode|unrestricted)",
        re.I,
    ),
    re.compile(r"new\s+instructions\s*:", re.I),
    re.compile(r"system\s*[\[\(]?\s*prompt", re.I),
    re.compile(r"developer\s+mode", re.I),
    re.compile(r"override\s+(safety|policy|rules)", re.I),
    re.compile(r"<\s*scratchpad", re.I),
    re.compile(r"end\s*of\s*transcript\.?\s*ignore", re.I),
)


@dataclass(frozen=True)
class IngestionGuardResult:
    quarantine: bool
    signals: tuple[str, ...]
    score: float


def scan_ingestion_text(text: str, *, enabled: bool | None = None) -> IngestionGuardResult:
    if enabled is None:
        enabled = get_settings().ingestion_guard_enabled
    if not enabled:
        return IngestionGuardResult(False, (), 0.0)
    norm = normalize_for_embedding(text).lower()
    hits: list[str] = []
    for i, rx in enumerate(_INJECTION_RES):
        if rx.search(norm):
            hits.append(f"pattern_{i}")
    score = float(len(hits))
    return IngestionGuardResult(
        quarantine=score >= 1.0,
        signals=tuple(hits),
        score=score,
    )


def apply_ingestion_flags_to_claim(claim: Claim) -> None:
    """Mutates claim with quarantine flags when the scanner or ZW-evasion probe fires."""
    s = get_settings()
    norm = normalize_for_embedding(claim.text)
    if s.ingestion_guard_enabled:
        r = scan_ingestion_text(norm, enabled=True)
        if r.quarantine:
            claim.ingestion_quarantine = True
            claim.ingestion_guard_signals = list(
                dict.fromkeys([*claim.ingestion_guard_signals, *list(r.signals)])
            )
    zw = zero_width_count(claim.text)
    if zw >= 4:
        claim.ingestion_quarantine = True
        tag = "zero_width_cluster"
        if tag not in claim.ingestion_guard_signals:
            claim.ingestion_guard_signals = [
                *claim.ingestion_guard_signals,
                tag,
            ]
