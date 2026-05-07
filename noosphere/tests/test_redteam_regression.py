"""CI regression: mitigated attack checks from noosphere.redteam."""

from __future__ import annotations

from noosphere.mitigations.coherence_judge_guard import judge_cited_scores_match_prior
from noosphere.models import (
    CoherenceVerdict,
    JudgePriorScoreRef,
    LLMJudgeVerdictPacket,
    SixLayerScore,
)
from noosphere.redteam import run_attack_suite


def test_mitigated_attack_suite_passes() -> None:
    out = run_attack_suite()
    assert out["attack_suite_version"]
    assert all(out["results"].values())


def test_single_attack_class_filter() -> None:
    out = run_attack_suite(attack_class="temporal_backdating")
    assert set(out["results"].keys()) == {"temporal_backdating"}


def test_judge_guard_accepts_legacy_six_layer_score_aliases() -> None:
    prior = SixLayerScore(consistency=0.11, argumentation=0.22)
    good = LLMJudgeVerdictPacket(
        verdict=CoherenceVerdict.UNRESOLVED,
        confidence=0.5,
        explanation="s1_consistency is 0.11 and s2_argumentation is 0.22.",
        cited_prior_scores=[
            JudgePriorScoreRef(layer="s1_consistency", value=0.11),
            JudgePriorScoreRef(layer="s2_argumentation", value=0.22),
        ],
    )
    bad = LLMJudgeVerdictPacket(
        verdict=CoherenceVerdict.UNRESOLVED,
        confidence=0.5,
        explanation="s1_consistency is 0.99 and s2_argumentation is 0.22.",
        cited_prior_scores=[
            JudgePriorScoreRef(layer="s1_consistency", value=0.99),
            JudgePriorScoreRef(layer="s2_argumentation", value=0.22),
        ],
    )

    assert prior.s1_consistency == 0.11
    assert prior.s2_argumentation == 0.22
    assert judge_cited_scores_match_prior(good, prior)
    assert not judge_cited_scores_match_prior(bad, prior)
