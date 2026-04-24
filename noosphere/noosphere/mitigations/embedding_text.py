"""Unicode normalization and low-tech embedding-evasion probes."""

from __future__ import annotations

import unicodedata

_ZW_CHARS = (
    "\u200b",  # ZWSP
    "\u200c",  # ZWNJ
    "\u200d",  # ZWJ
    "\ufeff",  # BOM
)


def normalize_for_embedding(text: str) -> str:
    """NFC + strip invisible joiners before encoding or pattern scans."""
    n = unicodedata.normalize("NFC", text or "")
    for ch in _ZW_CHARS:
        n = n.replace(ch, "")
    return n.strip()


def zero_width_count(text: str) -> int:
    """Count invisible characters that are often used to perturb embeddings."""
    return sum(text.count(ch) for ch in _ZW_CHARS)
