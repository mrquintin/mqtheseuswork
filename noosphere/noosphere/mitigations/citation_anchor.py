"""Fuzzy anchoring of a quoted span to a source document (citation forgery resistance)."""

from __future__ import annotations

import re


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 2}


def fuzzy_quote_plausible(quote: str, source: str, *, min_jaccard: float = 0.25) -> bool:
    """
    Cheap token-overlap gate: fabricated quotes that share no vocabulary with the
    source should fail until a human attaches a real pointer.
    """
    qt, st = _tokens(quote), _tokens(source)
    if not qt:
        return False
    inter = len(qt & st)
    union = len(qt | st) or 1
    return (inter / union) >= min_jaccard
