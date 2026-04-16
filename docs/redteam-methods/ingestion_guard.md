# Method note: ingestion guard (SP08)

## Purpose

Flag obvious **instruction-override** tropes in text that will flow into claim extraction, embeddings, or LLM-backed tools.

## Implementation

- Normalizes text (NFC, strips zero-width joiners) before pattern matching.
- Regex library in `noosphere/mitigations/ingestion_guard.py` (version with `ATTACK_SUITE_VERSION` in `redteam.py`).
- On hit: sets `Claim.ingestion_quarantine=True` and appends signal ids to `ingestion_guard_signals`. VTT `Chunk.metadata` uses string keys `ingestion_quarantine` / `ingestion_guard_signals`.

## False positives

Benign academic discussion should **not** match; covered by `noosphere/tests/redteam/test_ingestion_guard_benign.py`.

## Limitations

Not a replacement for a trained injection classifier or HITL review. Quarantine means **pause automation**, not automatic deletion.
