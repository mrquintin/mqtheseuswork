"""
``noosphere.core`` — foundational primitives (models, store, ledger, orchestrator,
observability, ids, config).

Round-19 module-hierarchy pass introduced this package as a stable public surface
for the lowest layer of the system. Implementations still live at their original
module paths (``noosphere.models``, ``noosphere.store``, …); this package
re-exports them so callers can write::

    from noosphere.core import Store, OntologyGraph, Ledger, get_logger

without coupling to the legacy flat layout. The legacy paths remain importable
and are the canonical implementation home until a follow-up prompt physically
moves the code; at that point this package becomes the source of truth and the
legacy paths become deprecation shims.
"""

from __future__ import annotations

from noosphere import config, ids, models, observability, orchestrator, store
from noosphere.ledger import (
    KeyRing,
    Ledger,
    PublicationKeyring,
    PublicationSignature,
    VerificationResult,
    VerifyReport,
    export_bundle,
    sign_publication,
    verify,
    verify_signature,
)
from noosphere.models import (
    Artifact,
    Chunk,
    Claim,
    ClaimOrigin,
    ClaimType,
    Episode,
    InputSourceType,
    Principle,
    Speaker,
)
from noosphere.observability import (
    Span,
    SpanRecorder,
    SpanStatus,
    configure_logging,
    current_span,
    current_trace,
    get_logger,
    get_recorder,
    set_recorder,
    start_span,
    start_trace,
)
from noosphere.orchestrator import NoosphereOrchestrator
from noosphere.ontology import OntologyGraph
from noosphere.store import Store

__all__ = [
    # Submodule passthroughs
    "config",
    "ids",
    "models",
    "observability",
    "orchestrator",
    "store",
    # Persistence
    "Store",
    "OntologyGraph",
    "NoosphereOrchestrator",
    # Ledger
    "KeyRing",
    "Ledger",
    "PublicationKeyring",
    "PublicationSignature",
    "VerificationResult",
    "VerifyReport",
    "export_bundle",
    "sign_publication",
    "verify",
    "verify_signature",
    # Core models
    "Artifact",
    "Chunk",
    "Claim",
    "ClaimOrigin",
    "ClaimType",
    "Episode",
    "InputSourceType",
    "Principle",
    "Speaker",
    # Observability
    "Span",
    "SpanRecorder",
    "SpanStatus",
    "configure_logging",
    "current_span",
    "current_trace",
    "get_logger",
    "get_recorder",
    "set_recorder",
    "start_span",
    "start_trace",
]
