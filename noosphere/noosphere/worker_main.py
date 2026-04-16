"""
Optional Python worker entrypoint (future: embeddings-only jobs, BYOK decrypt, etc.).

Ingest + synthesis for uploads is handled by the Founder Portal Redis worker
(``npm run worker:ingest``) so the web tier stays stateless and DB logs stay consistent.

This module is a placeholder CLI so a ``noosphere-worker`` container has a stable binary.
"""

from __future__ import annotations

from noosphere.observability import configure_logging, get_logger

log = get_logger(__name__)


def main() -> None:
    configure_logging(json_format=True)
    log.warning(
        "worker_main_placeholder",
        message="Use founder-portal `npm run worker:ingest` for Redis-backed ingest. "
        "Extend this module for Python-only background tasks.",
    )


if __name__ == "__main__":
    main()
