"""Voice corpus ingest, canonical keys, and relative-position maps."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from noosphere.coherence.aggregator import CoherenceAggregator
from noosphere.coherence.nli import StubNLIScorer
from noosphere.models import (
    ClaimOrigin,
    ConfidenceTier,
    Conclusion,
    voice_canonical_key,
)
from noosphere.store import Store
from noosphere.voices import compute_relative_position_map, ingest_path_as_voice

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VOICE_CORPUS = FIXTURES / "voice_corpus_public_domain.txt"


def _store(tmp_path) -> Store:
    return Store.from_database_url(f"sqlite:///{tmp_path / 'voices.db'}")


def test_voice_canonical_key_normalizes_punctuation() -> None:
    assert voice_canonical_key("Marx (Capital)") == "marx_capital"
    assert voice_canonical_key("  Habermas  ") == "habermas"


def test_ingest_path_as_voice_stub_claims(tmp_path) -> None:
    store = _store(tmp_path)
    aid, n = ingest_path_as_voice(
        store,
        VOICE_CORPUS,
        "Fixture Voice",
        copyright_status="test-fixture",
    )
    assert aid
    assert n >= 1
    voices = store.list_voice_profiles()
    assert len(voices) == 1
    v = voices[0]
    assert v.canonical_name == "Fixture Voice"
    assert aid in v.corpus_artifact_ids
    claims = store.list_claims_for_voice(v.id, limit=50)
    assert len(claims) >= 1
    assert all(c.claim_origin == ClaimOrigin.VOICE for c in claims)
    assert all(c.voice_id == v.id for c in claims)


def test_compute_relative_position_map_persists(tmp_path) -> None:
    store = _store(tmp_path)
    ingest_path_as_voice(store, VOICE_CORPUS, "Map Voice", copyright_status="test")
    cid = "conc-voice-1"
    store.put_conclusion(
        Conclusion(
            id=cid,
            text="We hold that clarity in language is a methodological obligation.",
            confidence_tier=ConfidenceTier.FIRM,
            rationale="test",
            supporting_principle_ids=[],
            evidence_chain_claim_ids=[],
            dissent_claim_ids=[],
            confidence=0.8,
            created_at=datetime.now(timezone.utc),
        )
    )
    agg = CoherenceAggregator(
        nli=StubNLIScorer(),
        skip_llm_judge=True,
        skip_probabilistic_llm=True,
    )
    m = compute_relative_position_map(store, cid, agg)
    assert m.conclusion_id == cid
    assert m.entries
    loaded = store.get_relative_position_map(cid)
    assert loaded is not None
    assert loaded.closest_agreeing_voice_id or loaded.closest_opposing_voice_id or loaded.entries
