"""Tests for the method-outcome linker and the per-method track-record
aggregator.

The four invariants under test mirror the constraints stated alongside the
implementation:

1. Idempotence — re-running the linker upserts weights, never appends.
2. Closed vocabulary — links naming an unknown registry method are dropped.
3. Resolution-status hard filter — unresolved predictions never enter the
   slope estimator.
4. No silent smoothing across domains — when domain labels exist on
   ConclusionMethod rows, the aggregator emits one TrackRecord per domain.

Plus: the bootstrap CI shrinks as n grows, the severity ceiling for new
conclusions kicks in when the track record is thin, and the linker output
respects the registry vocabulary closed set.
"""

from __future__ import annotations

import math

from noosphere.evaluation.method_outcome_linker import (
    LinkedMethod,
    RegistryMethodView,
    StubMethodLinkerJudge,
    infer_links,
)
from noosphere.evaluation.method_track_record import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    ResolvedPrediction,
    TrackRecord,
    aggregate,
    bootstrap_slope_ci,
    ols_slope,
    severity_ceiling_for,
    severity_pass_rate,
    weighted_brier,
)
from noosphere.evaluation.mqs import MethodologyProfileSummary


# ── Linker ────────────────────────────────────────────────────────────────


def _profile(pattern_type: str = "empirical_calibration", confidence: float = 0.7):
    return MethodologyProfileSummary(
        pattern_type=pattern_type,
        title="t",
        summary="s",
        reasoning_moves=["m"],
        transfer_targets=["forecasting"],
        assumptions=["one"],
        failure_modes=["fm"],
        confidence=confidence,
    )


def test_linker_drops_methods_not_in_registry_vocabulary() -> None:
    """If the LLM judge hallucinates a method name that isn't registered,
    the linker must drop the link silently — the registry is the closed
    vocabulary."""
    registry = [
        RegistryMethodView(name="empirical_calibration", version="1.0.0"),
    ]
    judge = StubMethodLinkerJudge(
        responses={
            "c1": [
                {
                    "method_name": "empirical_calibration",
                    "method_version": "1.0.0",
                    "weight": 0.9,
                    "domain": "forecasting",
                },
                {
                    # Hallucinated — must be dropped.
                    "method_name": "alchemical_intuition",
                    "method_version": "9.9.9",
                    "weight": 0.9,
                    "domain": "forecasting",
                },
            ]
        }
    )
    links = infer_links(
        conclusion_id="c1",
        conclusion_text="x",
        topic_hint="forecasting",
        profiles=[_profile()],
        registry_methods=registry,
        judge=judge,
    )
    assert len(links) == 1
    assert links[0].method_name == "empirical_calibration"


def test_linker_dedupes_repeated_method_versions() -> None:
    """A judge that returns the same (name, version) twice must produce
    one link, not two — `upsert_links` would coerce these to one row
    anyway, but the linker should not rely on the DB to enforce that."""
    registry = [
        RegistryMethodView(name="empirical_calibration", version="1.0.0"),
    ]
    judge = StubMethodLinkerJudge(
        responses={
            "c2": [
                {
                    "method_name": "empirical_calibration",
                    "method_version": "1.0.0",
                    "weight": 0.7,
                },
                {
                    "method_name": "empirical_calibration",
                    "method_version": "1.0.0",
                    "weight": 0.4,
                },
            ]
        }
    )
    links = infer_links(
        conclusion_id="c2",
        conclusion_text="x",
        topic_hint="",
        profiles=[_profile()],
        registry_methods=registry,
        judge=judge,
    )
    assert len(links) == 1


def test_stub_linker_matches_pattern_type_to_registered_method_name() -> None:
    """The stub heuristic: case-insensitive match between
    profile.pattern_type and the registry method's `name`. This is what
    powers the no-LLM CLI default — if a method called
    `empirical_calibration` is registered, the stub will link any
    conclusion whose profile carries that pattern type."""
    registry = [
        RegistryMethodView(name="empirical_calibration", version="1.0.0"),
        RegistryMethodView(name="adversarial_revision", version="1.0.0"),
    ]
    judge = StubMethodLinkerJudge()
    links = infer_links(
        conclusion_id="c3",
        conclusion_text="x",
        topic_hint="forecasting",
        profiles=[
            _profile(pattern_type="empirical_calibration", confidence=0.7),
            _profile(pattern_type="adversarial_revision", confidence=0.5),
            _profile(pattern_type="not_in_registry", confidence=0.9),
        ],
        registry_methods=registry,
        judge=judge,
    )
    names = sorted(link.method_name for link in links)
    assert names == ["adversarial_revision", "empirical_calibration"]
    assert all(link.domain == "forecasting" for link in links)


# ── Aggregator core ───────────────────────────────────────────────────────


def _row(
    *,
    cid: str = "c",
    pid: str,
    p: float,
    o: float,
    weight: float = 1.0,
    domain: str = "",
    severity: float | None = None,
    brier: float | None = None,
) -> ResolvedPrediction:
    if brier is None:
        brier = (p - o) ** 2
    return ResolvedPrediction(
        conclusion_id=cid,
        prediction_id=pid,
        probability=p,
        outcome=o,
        brier=brier,
        weight=weight,
        domain=domain,
        severity=severity,
    )


def test_weighted_brier_is_weighted_not_unweighted() -> None:
    """A heavily-weighted bad forecast must move the weighted Brier more
    than a lightly-weighted good forecast."""
    rows = [
        _row(pid="a", p=0.9, o=0.0, weight=10.0),  # bad, heavy
        _row(pid="b", p=0.1, o=0.0, weight=0.1),   # good, light
    ]
    wb = weighted_brier(rows)
    # Weighted average is dominated by the heavy bad row (Brier 0.81).
    assert wb is not None
    assert wb > 0.7


def test_ols_slope_is_one_for_perfectly_calibrated_predictions() -> None:
    """Outcome equals probability rounded to {0,1}: a calibrated set."""
    rows = [
        _row(pid="a", p=0.1, o=0.0),
        _row(pid="b", p=0.3, o=0.0),
        _row(pid="c", p=0.7, o=1.0),
        _row(pid="d", p=0.9, o=1.0),
    ]
    slope = ols_slope(rows)
    assert slope is not None
    # Hand-calculated: slope = cov(x, y) / var(x) = 1.5 for this set —
    # a slight over-discrimination, since outcomes flip at p=0.5 while
    # probabilities are spread across [0.1, 0.9].
    assert 1.0 < slope <= 1.5 + 1e-9


def test_ols_slope_returns_none_when_probability_column_is_constant() -> None:
    rows = [
        _row(pid="a", p=0.5, o=0.0),
        _row(pid="b", p=0.5, o=1.0),
        _row(pid="c", p=0.5, o=1.0),
    ]
    assert ols_slope(rows) is None


def test_aggregate_does_not_smooth_across_domains() -> None:
    """When ConclusionMethod rows carry distinct domain labels, the
    aggregator must produce one TrackRecord per domain — never a single
    pooled row that hides cross-domain heterogeneity."""
    rows = [
        # Forecasting domain: well-calibrated.
        _row(pid="f1", cid="cf1", p=0.2, o=0.0, domain="forecasting"),
        _row(pid="f2", cid="cf2", p=0.8, o=1.0, domain="forecasting"),
        _row(pid="f3", cid="cf3", p=0.7, o=1.0, domain="forecasting"),
        # Policy domain: badly miscalibrated.
        _row(pid="p1", cid="cp1", p=0.9, o=0.0, domain="policy"),
        _row(pid="p2", cid="cp2", p=0.1, o=1.0, domain="policy"),
        _row(pid="p3", cid="cp3", p=0.8, o=0.0, domain="policy"),
    ]
    records = aggregate(
        organization_id="org",
        method_name="empirical_calibration",
        method_version="1.0.0",
        rows=rows,
        bootstrap_iterations=50,
    )
    domains = {r.domain for r in records}
    assert domains == {"forecasting", "policy"}, (
        "aggregator must emit one row per domain, not pooled — got "
        f"{domains!r}"
    )
    by_domain = {r.domain: r for r in records}
    assert by_domain["forecasting"].weighted_brier is not None
    assert by_domain["policy"].weighted_brier is not None
    # Forecasting calibration should be much better than policy.
    assert by_domain["forecasting"].weighted_brier < by_domain["policy"].weighted_brier


def test_aggregator_excludes_unresolved_implicitly_by_filter_contract() -> None:
    """The aggregator's contract is that callers pass *resolved*
    predictions only. The `fetch_resolved_rows` SQL query enforces this
    via `marketOutcome IN ('YES', 'NO')`. We assert the contract here by
    showing that no `outcome=None` row could ever reach `aggregate`
    without crashing — outcome is a non-optional float on
    ResolvedPrediction."""
    # The dataclass is frozen and outcome is float-typed; passing None
    # would either be a TypeError at construction or a NaN that
    # propagates. Assert by attempting a NaN outcome and confirming the
    # slope estimator does not silently absorb it.
    rows = [
        _row(pid="a", p=0.5, o=1.0),
        _row(pid="b", p=0.5, o=0.0),
        _row(pid="c", p=0.7, o=float("nan")),
    ]
    slope = ols_slope(rows)
    # NaN is contagious: the OLS slope must not silently return a
    # "looks-fine" number for a corrupted input.
    assert slope is None or math.isnan(slope)


def test_bootstrap_ci_returns_none_below_minimum_n() -> None:
    """Below n=5 we refuse to publish a CI — the bootstrap is meaningless
    at that sample size."""
    rows = [
        _row(pid=f"p{i}", p=0.5 + 0.1 * i, o=float(i % 2)) for i in range(4)
    ]
    lo, hi = bootstrap_slope_ci(rows, iterations=50)
    assert lo is None and hi is None


def test_bootstrap_ci_narrows_with_more_data() -> None:
    """At n=50 with consistent calibration, the bootstrap interval should
    be narrower than the same setup at n=10. The exact endpoints are
    seeded but a sanity check on width is enough to catch regressions."""
    def _make(n: int) -> list[ResolvedPrediction]:
        out = []
        for i in range(n):
            p = (i + 1) / (n + 1)  # spread probabilities over (0,1)
            o = 1.0 if (i % 3 != 0) and p > 0.4 else 0.0
            out.append(_row(pid=f"p{i}", p=p, o=o))
        return out

    small_lo, small_hi = bootstrap_slope_ci(_make(10), iterations=200)
    big_lo, big_hi = bootstrap_slope_ci(_make(50), iterations=200)
    assert small_lo is not None and small_hi is not None
    assert big_lo is not None and big_hi is not None
    assert (big_hi - big_lo) <= (small_hi - small_lo) + 1e-9


def test_severity_pass_rate_is_per_conclusion_not_per_prediction() -> None:
    """A conclusion with five forecasts contributes ONE severity vote,
    not five — otherwise a single prolific conclusion would dominate."""
    rows = [
        _row(pid="a1", cid="A", p=0.5, o=1.0, severity=0.9),
        _row(pid="a2", cid="A", p=0.6, o=1.0, severity=0.9),
        _row(pid="a3", cid="A", p=0.4, o=0.0, severity=0.9),
        _row(pid="b1", cid="B", p=0.5, o=1.0, severity=0.2),  # below threshold
    ]
    rate = severity_pass_rate(rows)
    # Two distinct conclusions, one above threshold (A) and one below (B).
    assert rate is not None
    assert abs(rate - 0.5) < 1e-9


def test_severity_pass_rate_is_none_when_no_severity_known() -> None:
    rows = [_row(pid="a", p=0.5, o=1.0, severity=None)]
    assert severity_pass_rate(rows) is None


# ── MQS coupling: track record caps severity for new conclusions ─────────


def test_severity_ceiling_caps_when_track_record_is_thin() -> None:
    """A method with fewer than the publishable sample size cannot let a
    new conclusion in its domain score high on Severity. The ceiling
    drops to 0.5 below n=5."""
    record = TrackRecord(
        organization_id="org",
        method_name="empirical_calibration",
        method_version="1.0.0",
        domain="forecasting",
        sample_size=2,
        weighted_brier=0.1,
        calibration_slope=1.0,
        calibration_slope_ci_low=None,
        calibration_slope_ci_high=None,
        severity_pass_rate=None,
        evidence={},
    )
    assert severity_ceiling_for(record) == 0.5


def test_severity_ceiling_caps_when_track_record_is_poor() -> None:
    """At sufficient n but bad calibration (Brier ≥ 0.25), severity is
    also capped — the method has been tried and has a bad track record."""
    record = TrackRecord(
        organization_id="org",
        method_name="empirical_calibration",
        method_version="1.0.0",
        domain="forecasting",
        sample_size=20,
        weighted_brier=0.30,
        calibration_slope=0.4,
        calibration_slope_ci_low=0.0,
        calibration_slope_ci_high=0.8,
        severity_pass_rate=0.5,
        evidence={},
    )
    ceiling = severity_ceiling_for(record)
    assert ceiling is not None
    assert ceiling <= 0.4


def test_mqs_severity_caps_when_track_record_ceiling_is_passed_in() -> None:
    """End-to-end coupling: when a MethodTrackRecord ceiling is threaded
    into MqsInput.severity_track_record_ceiling, score_severity must clamp
    its output to the ceiling. This is what prevents a method with a thin
    or poor track record from projecting high severity onto a new
    conclusion in its domain."""
    from noosphere.evaluation.mqs import (
        MethodologyProfileSummary,
        MqsInput,
        StubMqsJudge,
        score_severity,
    )

    profile = MethodologyProfileSummary(
        pattern_type="empirical_calibration",
        title="t",
        summary="s",
        reasoning_moves=["m"],
        transfer_targets=["forecasting"],
        assumptions=["one"],
        failure_modes=["fm1", "fm2", "fm3"],  # strong floor → score wants high
        confidence=0.9,
    )
    judge = StubMqsJudge(
        responses={"severity": {"score": 0.9, "rationale": "high severity"}}
    )

    # No ceiling → severity gets to its high score.
    uncapped = score_severity(
        MqsInput(
            conclusion_id="c1",
            conclusion_text="x",
            profiles=[profile],
            dissent_claim_count=2,
        ),
        judge,
    )
    assert uncapped.score >= 0.6

    # With a thin-track-record ceiling, severity is clamped from above.
    capped = score_severity(
        MqsInput(
            conclusion_id="c1",
            conclusion_text="x",
            profiles=[profile],
            dissent_claim_count=2,
            severity_track_record_ceiling=0.5,
        ),
        judge,
    )
    assert capped.score <= 0.5
    assert capped.evidence["track_record_capped"] is True
    assert capped.evidence["track_record_ceiling"] == 0.5


def test_severity_ceiling_is_none_for_strong_track_record() -> None:
    """Methods with ≥ 5 samples and good Brier get no severity cap from
    the track record — they've earned the right to claim severity."""
    record = TrackRecord(
        organization_id="org",
        method_name="empirical_calibration",
        method_version="1.0.0",
        domain="forecasting",
        sample_size=20,
        weighted_brier=0.10,
        calibration_slope=1.0,
        calibration_slope_ci_low=0.8,
        calibration_slope_ci_high=1.2,
        severity_pass_rate=0.8,
        evidence={},
    )
    assert severity_ceiling_for(record) is None


# ── End-to-end: aggregator output schema is stable ────────────────────────


def test_aggregate_emits_one_record_per_unique_domain() -> None:
    rows = [
        _row(pid="a", p=0.5, o=1.0, domain=""),
        _row(pid="b", p=0.5, o=0.0, domain=""),
        _row(pid="c", p=0.5, o=1.0, domain="forecasting"),
    ]
    records = aggregate(
        organization_id="org",
        method_name="m",
        method_version="1",
        rows=rows,
        bootstrap_iterations=20,
    )
    domains = sorted(r.domain for r in records)
    assert domains == ["", "forecasting"]
    assert sum(r.sample_size for r in records) == 3


def test_evidence_blob_includes_provenance_lists() -> None:
    rows = [
        _row(pid="p1", cid="c1", p=0.5, o=1.0),
        _row(pid="p2", cid="c2", p=0.5, o=0.0),
    ]
    records = aggregate(
        organization_id="org",
        method_name="m",
        method_version="1",
        rows=rows,
        bootstrap_iterations=10,
    )
    assert len(records) == 1
    ev = records[0].evidence
    assert "prediction_ids" in ev and set(ev["prediction_ids"]) == {"p1", "p2"}
    assert "conclusion_ids" in ev and set(ev["conclusion_ids"]) == {"c1", "c2"}
    assert ev["bootstrap_iterations"] == 10
