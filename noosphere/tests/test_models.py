"""Strict boundary models: JSON round-trip and invalid payload rejection."""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from noosphere.models import (
    Artifact,
    Chunk,
    Claim,
    ClaimType,
    CoherenceVerdict,
    Conclusion,
    ConfidenceTier,
    DriftEvent,
    Entity,
    ResearchSuggestion,
    SixLayerScore,
    Speaker,
    Topic,
)


def test_artifact_roundtrip() -> None:
    a = Artifact(
        id="art_x",
        uri="file:///x.txt",
        mime_type="text/plain",
        byte_length=3,
        content_sha256="ab" * 32,
    )
    b = Artifact.model_validate_json(a.model_dump_json())
    assert b == a


def test_artifact_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Artifact.model_validate(
            {
                "id": "art_x",
                "uri": "",
                "mime_type": "",
                "byte_length": 0,
                "content_sha256": "",
                "created_at": datetime.now().isoformat(),
                "nope": 1,
            }
        )


def test_chunk_roundtrip() -> None:
    c = Chunk(
        id="chk_1",
        artifact_id="art_x",
        start_offset=0,
        end_offset=10,
        text="hello world",
    )
    assert Chunk.model_validate_json(c.model_dump_json()) == c


def test_claim_roundtrip_with_type() -> None:
    sp = Speaker(name="Ada", role="founder")
    cl = Claim(
        text="Markets clear.",
        speaker=sp,
        episode_id="ep_1",
        episode_date=date(2024, 1, 1),
        claim_type=ClaimType.METHODOLOGICAL,
        chunk_id="chk_1",
        confidence=0.9,
    )
    out = Claim.model_validate_json(cl.model_dump_json())
    assert out.claim_type == ClaimType.METHODOLOGICAL
    assert out.chunk_id == "chk_1"


def test_claim_rejects_wrong_enum_string() -> None:
    base = {
        "id": "c1",
        "text": "x",
        "speaker": {"name": "A", "role": "founder"},
        "episode_id": "e",
        "episode_date": "2024-01-01",
        "claim_type": "not-a-real-type",
    }
    with pytest.raises(ValidationError):
        Claim.model_validate(base)


def test_entity_topic_roundtrip() -> None:
    e = Entity(id="ent_1", label="ACME", entity_type="org")
    t = Topic(id="top_1", label="Strategy", description="How to decide")
    assert Entity.model_validate_json(e.model_dump_json()) == e
    assert Topic.model_validate_json(t.model_dump_json()) == t


def test_coherence_verdict_values() -> None:
    assert CoherenceVerdict("unresolved") == CoherenceVerdict.UNRESOLVED


def test_six_layer_score_roundtrip() -> None:
    s = SixLayerScore(
        s1_consistency=0.8,
        s2_argumentation=0.7,
        s3_probabilistic=0.6,
        s4_geometric=0.5,
        s5_compression=0.4,
        s6_llm_judge=0.3,
    )
    assert SixLayerScore.model_validate_json(s.model_dump_json()) == s


def test_conclusion_confidence_tier() -> None:
    c = Conclusion(
        text="We hold X tentatively.",
        confidence_tier=ConfidenceTier.OPEN,
        rationale="Sparse evidence",
    )
    d = Conclusion.model_validate_json(c.model_dump_json())
    assert d.confidence_tier == ConfidenceTier.OPEN


def test_drift_event_roundtrip() -> None:
    d = DriftEvent(
        target_id="pr_1",
        observed_at=date(2025, 6, 1),
        drift_score=0.12,
        notes="shift",
    )
    assert DriftEvent.model_validate_json(d.model_dump_json()).target_id == "pr_1"


def test_research_suggestion_roundtrip() -> None:
    r = ResearchSuggestion(
        title="Read Kuhn",
        summary="Paradigms",
        rationale="Method talk",
        reading_uris=["https://example.invalid/book"],
    )
    assert ResearchSuggestion.model_validate_json(r.model_dump_json()).title == "Read Kuhn"
