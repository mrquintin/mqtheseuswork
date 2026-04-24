"""
Deterministic, content-addressed identifiers for domain objects.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact_id_from_bytes(content: bytes) -> str:
    """Stable ID for an artifact from raw file bytes (content hash)."""
    return f"art_{_sha256_hex(content)}"


def artifact_id_from_file(path: str | Path) -> str:
    """Read file bytes and compute artifact ID (idempotent for same path+content)."""
    p = Path(path)
    return artifact_id_from_bytes(p.read_bytes())


def chunk_id(artifact_id: str, start_offset: int, end_offset: int) -> str:
    """Chunk ID from artifact and byte span (inclusive start, exclusive end)."""
    key = f"{artifact_id}:{start_offset}:{end_offset}".encode()
    return f"chk_{_sha256_hex(key)}"


def normalize_claim_text(text: str) -> str:
    """Normalize claim text before hashing (stable across trivial whitespace)."""
    return " ".join(text.strip().split())


def claim_text_hash(normalized_text: str) -> str:
    return _sha256_hex(normalized_text.encode("utf-8"))


def claim_id(chunk_id_value: str, normalized_claim_text: str) -> str:
    """Claim ID from parent chunk and normalized proposition text."""
    nh = claim_text_hash(normalized_claim_text)
    key = f"{chunk_id_value}:{nh}".encode()
    return f"clm_{_sha256_hex(key)}"


# ── Currents (Wave 1): Current-events identifiers ──────────────────────────


def make_id(namespace: str, *parts: str) -> str:
    key = "|".join(parts).encode("utf-8")
    return f"{namespace}_{_sha256_hex(key)}"


def make_event_id(dedupe_hash: str) -> str:
    return make_id("event", dedupe_hash)


def make_opinion_id(event_id: str, model_name: str, generated_at_iso: str) -> str:
    return make_id("opinion", event_id, model_name, generated_at_iso)


def make_citation_id(opinion_id: str, ordinal: int) -> str:
    return make_id("cite", opinion_id, str(ordinal))


def make_followup_session_id(opinion_id: str, client_fingerprint: str, day_iso: str) -> str:
    return make_id("fus", opinion_id, client_fingerprint, day_iso)


def make_followup_message_id(session_id: str, ordinal: int) -> str:
    return make_id("fum", session_id, str(ordinal))


def make_followup_citation_id(message_id: str, ordinal: int) -> str:
    """ID for a citation produced by a follow-up assistant message.

    Uses the ``fucite`` namespace (distinct from ``cite`` used by
    ``make_citation_id`` for original opinion citations) so the two id
    spaces cannot collide.
    """
    return make_id("fucite", message_id, str(ordinal))
