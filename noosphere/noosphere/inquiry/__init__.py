"""
``noosphere.inquiry`` — epistemic-quality machinery: coherence checks, calibrated
evaluation, peer review, red-team, and the shipped mitigations that defend the
inference path.

Round-19 hierarchy pass introduced this package as a stable surface for the
inquiry-layer subpackages. The concrete implementations still live at
``noosphere.coherence``, ``noosphere.evaluation``, ``noosphere.peer_review``,
``noosphere.redteam``, and ``noosphere.mitigations``; this package re-exports
them so callers can write ``from noosphere.inquiry import coherence`` without
needing to know the legacy flat layout.

Layering rule (enforced by ``.import-linter``): ``inquiry`` may import from
``core`` and ``methods``; it may *not* import from ``cli``, ``io``, or
``literature``.
"""

from __future__ import annotations

from noosphere import coherence, evaluation, mitigations, peer_review, redteam

__all__ = [
    "coherence",
    "evaluation",
    "mitigations",
    "peer_review",
    "redteam",
]
