from __future__ import annotations

from noosphere.methodology import derive_methodology_profiles
from noosphere.methods._registry import REGISTRY
from noosphere.methods.extract_methodology import (
    ExtractMethodologyInput,
    extract_methodology,
)


TEXT = """
We should not treat the school as a fixed category; the purpose has to be
reduced to first principles, constraints, and what education is for. The useful
question is how we came to the conclusion, because that frame can transfer to
other institutions and unrelated systems. A serious objection is that the
analogy could be superficial, so the method has to name failure modes and what
evidence would change our confidence.
"""


def test_derive_methodology_profiles_captures_method_not_just_topic() -> None:
    profiles = derive_methodology_profiles(TEXT, source_title="method transcript")

    pattern_types = {profile.pattern_type for profile in profiles}
    assert "first_principles_decomposition" in pattern_types
    assert "analogical_transfer" in pattern_types
    assert "adversarial_revision" in pattern_types
    assert all(profile.reasoning_moves for profile in profiles)
    assert all(profile.transfer_targets for profile in profiles)
    assert all(profile.assumptions for profile in profiles)
    assert all(profile.failure_modes for profile in profiles)
    assert all(profile.evidence_anchors for profile in profiles)


def test_source_anchors_preserve_line_wrapped_sentences() -> None:
    profiles = derive_methodology_profiles(TEXT, source_title="method transcript")

    assert any(
        "purpose has to be reduced to first principles" in anchor["quote"]
        for profile in profiles
        for anchor in profile.evidence_anchors
    )
    assert all(
        anchor["sourceTitle"] == "method transcript"
        for profile in profiles
        for anchor in profile.evidence_anchors
    )


def test_transfer_targets_do_not_smuggle_education_as_target_domain() -> None:
    profiles = derive_methodology_profiles(TEXT, source_title="method transcript")

    targets = {
        target
        for profile in profiles
        for target in profile.transfer_targets
    }
    assert "institutional design" in targets
    assert "education" not in targets


def test_registered_extract_methodology_method_uses_same_contract() -> None:
    out = extract_methodology(
        ExtractMethodologyInput(text=TEXT, source_title="method transcript")
    )

    assert out.profiles
    first = out.profiles[0]
    assert first.title
    assert first.summary
    assert first.reasoning_moves
    assert first.transfer_targets
    assert first.assumptions
    assert first.failure_modes
    assert first.evidence_anchors


def test_extract_methodology_is_registered_as_deterministic_noosphere_method() -> None:
    spec, fn = REGISTRY.get("extract_methodology")

    assert spec.name == "extract_methodology"
    assert spec.nondeterministic is False
    assert fn is extract_methodology
