"""Calibration integrity helpers (gold signing is operational policy; helpers here are hooks)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def gold_bundle_canonical_fingerprint(rows: list[dict[str, Any]]) -> str:
    """Stable SHA-256 over a canonical JSON representation (for signed gold bundles)."""
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def calibration_rows_look_gamed(
    rows: list[tuple[float, float]],
    *,
    narrow_width: float = 0.06,
    suspicious_fraction: float = 0.35,
) -> bool:
    """
    Detect trivial interval-narrowing games across many predictions.

    rows: (prob_low, prob_high) before midpoint resolution.
    """
    if len(rows) < 8:
        return False
    narrow = sum(1 for lo, hi in rows if abs(float(hi) - float(lo)) < narrow_width)
    return (narrow / len(rows)) >= suspicious_fraction
