"""Red-team tournament harness.

Verifies the invariants the leaderboard depends on:

* config_id is content-addressable — same provider mix / prompt /
  temperature / seed produces the same id, label changes do not,
* the harness rejects duplicate config ids,
* per-configuration severity-weighted scores aggregate correctly,
* cross-validation reads "given A's high-severity items, did B
  reproduce them?", with a 1.0 score when A flagged nothing,
* the leaderboard surfaces the reproducibility envelope hash on
  every row and refuses to mark partial-runs reproducible,
* the bench loader round-trips the frozen JSONL plus its sha256.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from noosphere.peer_review.providers import ObjectionResult
from noosphere.peer_review.severity import (
    ObjectionSeverity,
    SeverityInputs,
    score_objection as score_objection_severity,
)
from noosphere.peer_review.tournament import (
    BenchItem,
    ReviewerConfig,
    bench_sha256,
    cross_validate,
    load_bench,
    run_tournament,
    write_tournament_result,
)


# ── Stub bench + driver ──────────────────────────────────────────────


def _stub_bench() -> list[BenchItem]:
    return [
        BenchItem(
            id="bench-001",
            text="Founder-led firms outperform on five-year ROIC.",
            reasoning="Cross-section, 2010-2020.",
            domain="economics",
            license="firm-internal-public",
            frozen_at="2026-05-08T00:00:00Z",
            confidence=0.78,
            severity_inputs=SeverityInputs(
                cascade_weight=0.85,
                claim_centrality=0.7,
                failure_mode_severity=0.5,
            ),
        ),
        BenchItem(
            id="bench-002",
            text="Geometric coherence is discriminative for contradiction.",
            reasoning="QH benchmark.",
            domain="ai",
            license="firm-internal-public",
            frozen_at="2026-05-08T00:00:00Z",
            confidence=0.62,
            severity_inputs=SeverityInputs(
                cascade_weight=0.6,
                claim_centrality=0.85,
                failure_mode_severity=0.4,
            ),
        ),
    ]


def _make_objection(provider: str, text: str, cost: float = 0.001) -> ObjectionResult:
    return ObjectionResult(
        provider=provider,
        model=f"{provider}-stub",
        text=text,
        cost_usd=cost,
        latency_ms=10.0,
        tokens_in=80,
        tokens_out=40,
    )


def _make_severity(*, judge_severity: Optional[float] = None) -> ObjectionSeverity:
    inp = SeverityInputs(
        cascade_weight=0.85,
        claim_centrality=0.85,
        failure_mode_severity=1.0,
        judge_severity=judge_severity,
    )
    return score_objection_severity(inp)


# ── Content-addressable config id ────────────────────────────────────


def test_config_id_is_content_addressable():
    a = ReviewerConfig(
        provider_mix=("anthropic", "openai"),
        prompt_variant="default",
        temperature=0.2,
        seed=42,
        label="diverse-pair",
    )
    b = ReviewerConfig(
        provider_mix=("openai", "anthropic"),  # order-insensitive
        prompt_variant="default",
        temperature=0.2,
        seed=42,
        label="other-label",  # label is display-only
        description="totally different description",
    )
    c = ReviewerConfig(
        provider_mix=("anthropic", "openai"),
        prompt_variant="default",
        temperature=0.5,  # different temperature → different id
        seed=42,
    )

    assert a.config_id == b.config_id
    assert a.config_id != c.config_id
    assert a.config_id.startswith("cfg-")


def test_run_tournament_rejects_duplicate_config_ids():
    bench = _stub_bench()
    cfg = ReviewerConfig(
        provider_mix=("anthropic",),
        prompt_variant="default",
        temperature=0.2,
        seed=1,
    )
    with pytest.raises(ValueError, match="duplicate config_id"):
        run_tournament(
            bench,
            [cfg, cfg],
            driver=lambda cfg, item: ([], [], False, None),
        )


# ── Cross-validation arithmetic ──────────────────────────────────────


def test_cross_validate_handles_empty_target():
    """If A flagged no high-severity items, B can't fail to reproduce."""
    from noosphere.peer_review.tournament import ConfigConclusionResult

    # Both configs return empty aggregates: both have no high-severity items.
    empty = ConfigConclusionResult(
        config_id="cfg-A",
        bench_item_id="bench-001",
        aggregate=None,
    )
    per_config = {
        "cfg-A": [empty],
        "cfg-B": [
            ConfigConclusionResult(
                config_id="cfg-B",
                bench_item_id="bench-001",
                aggregate=None,
            )
        ],
    }
    cells = cross_validate(per_config)
    # Two ordered pairs, both score 1.0 (no targets).
    assert {(c.config_a, c.config_b) for c in cells} == {
        ("cfg-A", "cfg-B"),
        ("cfg-B", "cfg-A"),
    }
    for c in cells:
        assert c.targets == 0
        assert c.score == 1.0


# ── End-to-end with a deterministic stub driver ──────────────────────


def test_run_tournament_full_pass_with_stub_driver(tmp_path):
    bench = _stub_bench()

    cfg_strict = ReviewerConfig(
        provider_mix=("anthropic", "openai"),
        prompt_variant="strict",
        temperature=0.2,
        seed=0,
        label="strict-pair",
        description="Anthropic + OpenAI, low-temperature.",
    )
    cfg_loose = ReviewerConfig(
        provider_mix=("gemini",),
        prompt_variant="loose",
        temperature=0.9,
        seed=0,
        label="gemini-loose",
        description="Solo Gemini, high-temperature.",
    )

    # Stub: cfg_strict raises a high-severity objection on both items.
    # cfg_loose only fires on bench-001 — agreement on cfg_strict
    # should be 0.5 (1 of 2 reproduced); agreement on cfg_loose should
    # be 1.0 (its single high-severity item is reproduced by strict).
    high = _make_severity()  # ceiling-driven, structurally high

    def stub_driver(cfg, item):
        if cfg.config_id == cfg_strict.config_id:
            obj = _make_objection("anthropic", "HIDDEN. assumption X.", cost=0.002)
            return ([obj], [high], False, None)
        # cfg_loose: only fires on bench-001.
        if item.id == "bench-001":
            obj = _make_objection("gemini", "HIDDEN. assumption Y.", cost=0.0005)
            return ([obj], [high], False, None)
        return ([], [], False, None)

    result = run_tournament(
        bench,
        [cfg_strict, cfg_loose],
        driver=stub_driver,
        bench_path=tmp_path / "stub_bench.jsonl",  # missing, falls back to id-hash
    )

    # Two leaderboard rows.
    assert len(result.leaderboard) == 2
    by_id = {row.config_id: row for row in result.leaderboard}
    strict_row = by_id[cfg_strict.config_id]
    loose_row = by_id[cfg_loose.config_id]

    assert strict_row.high_count == 2
    assert loose_row.high_count == 1
    assert strict_row.bench_items_reviewed == 2

    # cfg_loose reproduces 1 of cfg_strict's 2 high-severity items.
    assert strict_row.agreement == pytest.approx(0.5)
    # cfg_strict reproduces cfg_loose's single high-severity item.
    assert loose_row.agreement == pytest.approx(1.0)

    # Costs aggregated.
    assert strict_row.cost_usd == pytest.approx(0.004)
    assert loose_row.cost_usd == pytest.approx(0.0005)

    # Envelope hash present and identical across rows.
    assert strict_row.envelope_hash.startswith("env-")
    assert strict_row.envelope_hash == loose_row.envelope_hash
    assert result.envelope.envelope_hash == strict_row.envelope_hash

    # The leaderboard sort puts the higher severity-weighted score
    # first when both rows are reproducible.
    assert result.leaderboard[0].config_id == cfg_strict.config_id

    # Cross-validation matrix has two ordered pairs.
    assert len(result.cross_validation) == 2
    pairs = {(c.config_a, c.config_b) for c in result.cross_validation}
    assert (cfg_strict.config_id, cfg_loose.config_id) in pairs
    assert (cfg_loose.config_id, cfg_strict.config_id) in pairs


def test_partial_runs_block_reproducible_flag(tmp_path):
    bench = _stub_bench()
    cfg = ReviewerConfig(
        provider_mix=("anthropic",),
        prompt_variant="default",
        temperature=0.2,
        seed=0,
    )
    high = _make_severity()

    def stub_driver(cfg, item):
        # First item partial; second item ok with high severity. The
        # leaderboard must mark this configuration not-reproducible.
        if item.id == "bench-001":
            return ([], [], True, "budget_exhausted")
        obj = _make_objection("anthropic", "HIDDEN. y.")
        return ([obj], [high], False, None)

    result = run_tournament(
        bench,
        [cfg],
        driver=stub_driver,
        bench_path=tmp_path / "missing.jsonl",
    )
    assert len(result.leaderboard) == 1
    row = result.leaderboard[0]
    assert row.partial_runs == 1
    assert row.reproducible is False


def test_archive_writes_self_describing_json(tmp_path):
    bench = _stub_bench()
    cfg = ReviewerConfig(
        provider_mix=("anthropic",),
        prompt_variant="default",
        temperature=0.2,
        seed=0,
    )
    result = run_tournament(
        bench,
        [cfg],
        driver=lambda cfg, item: (
            [_make_objection("anthropic", "HIDDEN. z.")],
            [_make_severity()],
            False,
            None,
        ),
        bench_path=tmp_path / "missing.jsonl",
    )
    out = write_tournament_result(result, tmp_path / "archive")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "leaderboard" in payload
    assert "cross_validation" in payload
    assert payload["envelope"]["envelope_hash"].startswith("env-")
    assert payload["envelope"]["bench_sha256"]


# ── Bench loader against the real v1 file ────────────────────────────


REPO_ROOT = Path(__file__).resolve().parents[2]
V1_BENCH = REPO_ROOT / "benchmarks" / "redteam" / "v1" / "conclusion_bench.jsonl"
V1_CARD = REPO_ROOT / "benchmarks" / "redteam" / "v1" / "card.md"


@pytest.mark.skipif(not V1_BENCH.exists(), reason="v1 bench not present")
def test_load_bench_v1_roundtrip():
    items = load_bench(V1_BENCH)
    assert len(items) >= 5
    assert all(item.id.startswith("redteam-v1-") for item in items)
    assert all(item.license == "firm-internal-public" for item in items)
    # Hash is stable byte-level.
    h1 = bench_sha256(V1_BENCH)
    h2 = bench_sha256(V1_BENCH)
    assert h1 == h2 and len(h1) == 64


@pytest.mark.skipif(not V1_CARD.exists(), reason="v1 card not present")
def test_v1_card_documents_freezing_date():
    text = V1_CARD.read_text(encoding="utf-8")
    assert "Freezing date" in text or "frozen on" in text
    assert "2026-05-08" in text
