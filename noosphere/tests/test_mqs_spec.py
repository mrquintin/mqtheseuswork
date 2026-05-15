"""MQS Specification v1.0.0 — compliance test.

This file is the executable counterpart of `docs/methods/MQS_Specification.md`
(and `.tex`). It exercises the *formal claims* the spec makes about the
composite — gating, monotonicity, identity under perfect inputs, totality —
and pins every boundary case the spec enumerates in its §6.

It is a property-based test in the Hypothesis style, but deliberately
**dependency-free**: `noosphere`'s `pyproject.toml` keeps the dependency set
minimal, and an auditable spec-compliance suite is better off exercising the
same fixed input grid on every run than a different random sample each time.
`_input_space()` is the "strategy" — a deterministic grid plus a seeded-random
sweep over `[0,1]^5` — and each `test_*` asserts a property over all of it.

Where a test name is referenced by the spec's §6 boundary cases, the name is
kept verbatim so a reviewer can cross-walk the prose and the code.
"""

from __future__ import annotations

import math
import random
import subprocess
import sys
from pathlib import Path

import pytest

from noosphere.evaluation.mqs import (
    COMPOSITE_TIERS,
    DS_GATE_THRESHOLD,
    SEVERITY_NO_FAILURE_MODES_CAP,
    SUBSCORE_WEIGHTS,
    DOMAIN_NO_FAILURE_MODES_FLOOR,
    MethodologyProfileSummary,
    MqsInput,
    StubMqsJudge,
    composite_score,
    composite_tier,
    score_conclusion,
)

# ── The "strategy": a deterministic grid + a seeded-random sweep ────────────

#: Sub-score values that bracket every interesting point: the endpoints, the
#: gate threshold and its immediate neighbours, and a few interior points.
_GRID = (
    0.0,
    DS_GATE_THRESHOLD - 1e-6,
    DS_GATE_THRESHOLD,
    DS_GATE_THRESHOLD + 1e-6,
    0.25,
    0.5,
    0.75,
    1.0,
)

#: A coarser grid for the 5-way product so the test stays fast.
_COARSE = (0.0, DS_GATE_THRESHOLD, 0.3, 0.7, 1.0)


def _input_space():
    """Yield (s_P, s_S, s_AMF, s_C, s_DS) tuples covering [0,1]^5.

    Part 1: the full product of the coarse grid (5**5 = 3125 points) — every
    combination of the structurally-interesting values.
    Part 2: 4000 seeded-random points so interior behaviour is exercised too.
    """
    for p in _COARSE:
        for s in _COARSE:
            for a in _COARSE:
                for c in _COARSE:
                    for d in _COARSE:
                        yield (p, s, a, c, d)
    rng = random.Random(20260514)  # fixed seed: same sweep every run
    for _ in range(4000):
        yield tuple(rng.random() for _ in range(5))


def _wgm(p: float, s: float, a: float, c: float) -> float:
    """Reference weighted geometric mean — the spec's Eq. (13), recomputed
    independently of the module under test."""
    if min(p, s, a, c) <= 0.0:
        return 0.0
    return (
        p ** SUBSCORE_WEIGHTS["progressivity"]
        * s ** SUBSCORE_WEIGHTS["severity"]
        * a ** SUBSCORE_WEIGHTS["aim_method_fit"]
        * c ** SUBSCORE_WEIGHTS["compressibility"]
    )


def _score(p: float, s: float, a: float, c: float, d: float) -> float:
    return composite_score(
        progressivity=p,
        severity=s,
        aim_method_fit=a,
        compressibility=c,
        domain_sensitivity=d,
    )


# ── Formal claim: gating ────────────────────────────────────────────────────


def test_gating_is_a_hard_piecewise_function_of_domain_sensitivity() -> None:
    """Spec §5 / Eq. (12): below the threshold the composite is exactly 0;
    at or above it, the composite is exactly the weighted geometric mean of
    the other four — Domain Sensitivity never scales the magnitude."""
    for p, s, a, c, d in _input_space():
        composite = _score(p, s, a, c, d)
        if d < DS_GATE_THRESHOLD:
            assert composite == 0.0, (
                f"gate should be closed: d={d} < {DS_GATE_THRESHOLD} but "
                f"composite={composite}"
            )
        else:
            assert composite == pytest.approx(_wgm(p, s, a, c), abs=1e-9), (
                f"gate open: composite should be wgm of the four; "
                f"d={d}, got {composite}, want {_wgm(p, s, a, c)}"
            )


def test_gate_boundary_is_closed_on_passing_side() -> None:
    """Spec §6.2: the gate condition is the strict inequality s_DS < theta,
    so s_DS == theta opens the gate and s_DS == theta - epsilon closes it."""
    just_below = _score(1.0, 1.0, 1.0, 1.0, DS_GATE_THRESHOLD - 1e-9)
    exactly_at = _score(1.0, 1.0, 1.0, 1.0, DS_GATE_THRESHOLD)
    assert just_below == 0.0
    assert exactly_at > 0.0
    assert exactly_at == pytest.approx(1.0, abs=1e-9)


# ── Formal claim: monotonicity ──────────────────────────────────────────────


def test_composite_is_monotone_in_each_non_gate_subscore() -> None:
    """Spec §5.1: the weighted geometric mean is monotone non-decreasing in
    every one of the four non-gate sub-scores. Raising any single sub-score,
    others held fixed, never lowers the composite."""
    rng = random.Random(11)
    for _ in range(3000):
        base = [rng.random() for _ in range(4)]
        d = DS_GATE_THRESHOLD + rng.random() * (1 - DS_GATE_THRESHOLD)
        for i in range(4):
            lo = list(base)
            hi = list(base)
            hi[i] = lo[i] + rng.random() * (1 - lo[i])  # hi[i] >= lo[i]
            c_lo = _score(*lo, d)
            c_hi = _score(*hi, d)
            assert c_hi >= c_lo - 1e-9, (
                f"not monotone in subscore {i}: {lo}->{c_lo}, {hi}->{c_hi}"
            )


def test_composite_is_monotone_in_domain_sensitivity() -> None:
    """Spec §5 / Eq. (12): the composite is non-decreasing in s_DS overall —
    it is 0 below the gate and a fixed non-negative value at or above it."""
    rng = random.Random(12)
    for _ in range(3000):
        p, s, a, c = (rng.random() for _ in range(4))
        ds = sorted(rng.random() for _ in range(2))
        c_lo = _score(p, s, a, c, ds[0])
        c_hi = _score(p, s, a, c, ds[1])
        assert c_hi >= c_lo - 1e-9, (
            f"not monotone in domain_sensitivity: d={ds}, {c_lo} -> {c_hi}"
        )


# ── Formal claim: identity under perfect inputs ─────────────────────────────


def test_identity_under_perfect_inputs() -> None:
    """Spec §5.1: wgm equals 1 iff every input is 1. With the gate open and
    all four non-gate sub-scores perfect, the composite is exactly 1.0."""
    assert _score(1.0, 1.0, 1.0, 1.0, 1.0) == 1.0
    assert _score(1.0, 1.0, 1.0, 1.0, DS_GATE_THRESHOLD) == 1.0
    # ...and strictly below 1 if any of the four is below 1 (gate open).
    rng = random.Random(13)
    for _ in range(2000):
        four = [rng.random() for _ in range(4)]
        composite = _score(*four, 1.0)
        if min(four) >= 1.0:
            assert composite == pytest.approx(1.0, abs=1e-9)
        else:
            assert composite < 1.0


def test_equal_subscores_pass_through_the_operator() -> None:
    """A weighted geometric mean of four equal values is that value: the
    operator does not distort a balanced score (Eq. 13, sum of weights = 1)."""
    for x in _GRID:
        composite = _score(x, x, x, x, 1.0)
        assert composite == pytest.approx(x, abs=1e-9)


# ── Formal claim: weakest link ──────────────────────────────────────────────


def test_zero_subscore_zeroes_composite() -> None:
    """Spec §6.4 / Eq. (14): a single zeroed non-gate sub-score drives the
    composite to 0 even with the gate wide open — no redemption."""
    for i in range(4):
        four = [1.0, 1.0, 1.0, 1.0]
        four[i] = 0.0
        assert _score(*four, 1.0) == 0.0
    # And it holds for every gate-open sample in the space, too.
    for p, s, a, c, d in _input_space():
        if d >= DS_GATE_THRESHOLD and min(p, s, a, c) == 0.0:
            assert _score(p, s, a, c, d) == 0.0


# ── Formal claim: totality and bounds ───────────────────────────────────────


def test_composite_is_total_and_bounded() -> None:
    """Spec §6.5: every input is clamped before any arithmetic, so the
    composite is always a real number in [0,1] — including for NaN, +/-inf,
    and out-of-range inputs."""
    pathological = [
        float("nan"),
        float("inf"),
        float("-inf"),
        -1.0,
        2.0,
        1e9,
    ]
    # NaN/inf/out-of-range in every position, against a normal backdrop.
    for bad in pathological:
        for pos in range(5):
            args = [0.5, 0.5, 0.5, 0.5, 0.5]
            args[pos] = bad
            composite = _score(*args)
            assert 0.0 <= composite <= 1.0
            assert not math.isnan(composite)
    # And the whole ordinary input space stays in range.
    for p, s, a, c, d in _input_space():
        composite = _score(p, s, a, c, d)
        assert 0.0 <= composite <= 1.0
        assert composite_tier(composite) in {t for t, _ in COMPOSITE_TIERS}


def test_nan_subscore_behaves_as_zero() -> None:
    """Spec §6.5: clamp maps NaN to 0, so a NaN non-gate sub-score zeroes the
    composite (gate open) and a NaN domain sensitivity closes the gate."""
    nan = float("nan")
    assert _score(nan, 1.0, 1.0, 1.0, 1.0) == 0.0  # NaN in the operator -> 0
    assert _score(1.0, 1.0, 1.0, 1.0, nan) == 0.0  # NaN domain -> gate closed


# ── Boundary cases via the full scorer (spec §6) ────────────────────────────


def _profile(**overrides) -> MethodologyProfileSummary:
    base = dict(
        pattern_type="empirical_calibration",
        title="Empirical calibration",
        summary="Asks what evidence would discipline the belief.",
        reasoning_moves=["convert posture into evidence thresholds"],
        transfer_targets=["forecasting"],
        assumptions=["a serious belief should expose what would defeat it"],
        failure_modes=["can quantify false precision when the channel is thin"],
        confidence=0.7,
    )
    base.update(overrides)
    return MethodologyProfileSummary(**base)


def test_no_profiles_every_subscore_is_defined() -> None:
    """Spec §6.1: with no methodology profiles attached, every sub-score
    still resolves to a defined, conservative number — none is undefined."""
    out = score_conclusion(
        MqsInput(conclusion_id="c-empty", conclusion_text="a bare claim."),
        judge=StubMqsJudge(),
    )
    for name in (
        "progressivity",
        "severity",
        "aim_method_fit",
        "compressibility",
        "domain_sensitivity",
    ):
        sub = getattr(out, name)
        assert 0.0 <= sub.score <= 1.0, f"{name} out of range: {sub.score}"
    # The spec's stated fallbacks for the empty-profile case:
    assert out.severity.score <= SEVERITY_NO_FAILURE_MODES_CAP
    assert out.aim_method_fit.score == 0.5  # rubric level 2, "cannot verify"
    assert out.compressibility.score == 1.0  # n = 0 -> n' = 1
    assert out.domain_sensitivity.score >= DOMAIN_NO_FAILURE_MODES_FLOOR
    assert 0.0 <= out.composite <= 1.0


def test_no_judge_is_fully_deterministic() -> None:
    """Spec §6.1: the no-LLM backfill path (judge=None) is fully
    deterministic — scoring the same conclusion twice gives identical
    numbers."""
    inp = MqsInput(
        conclusion_id="c-det",
        conclusion_text="we will exit if MAU < 10k by 2027",
        rationale="if growth flattens then the thesis breaks",
        topic_hint="forecasting",
        profiles=[_profile()],
        forecast_count=2,
        has_check_back_date=True,
        dissent_claim_count=1,
    )
    a = score_conclusion(inp, judge=None)
    b = score_conclusion(inp, judge=None)
    assert a.composite == b.composite
    for name in (
        "progressivity",
        "severity",
        "aim_method_fit",
        "compressibility",
        "domain_sensitivity",
    ):
        assert getattr(a, name).score == getattr(b, name).score


def test_deterministic_verdicts_override_llm() -> None:
    """Spec §6.3: when a deterministic signal and the LLM judge disagree, the
    deterministic signal wins, toward caution."""
    # out_of_bounds verdict beats a judge that loves the domain.
    pin_high = StubMqsJudge(
        responses={
            "severity": {"score": 1.0, "rationale": "stub"},
            "aim_method_fit": {"score": 1.0, "rationale": "stub"},
            "compressibility": {"score": 1.0, "rationale": "stub"},
            "domain_sensitivity": {"score": 1.0, "rationale": "stub"},
        }
    )
    oob = score_conclusion(
        MqsInput(
            conclusion_id="c-oob",
            conclusion_text="we will revisit by 2027",
            profiles=[_profile()],
            forecast_count=2,
            has_check_back_date=True,
            domain_bound_verdict="out_of_bounds",
        ),
        judge=pin_high,
    )
    assert oob.domain_sensitivity.score == 0.0
    assert oob.composite == 0.0

    # No-failure-modes cap beats a judge that rates severity 1.0.
    no_fm = score_conclusion(
        MqsInput(
            conclusion_id="c-nofm",
            conclusion_text="a claim",
            profiles=[_profile(failure_modes=[], assumptions=[])],
            dissent_claim_count=0,
        ),
        judge=pin_high,
    )
    assert no_fm.severity.score <= SEVERITY_NO_FAILURE_MODES_CAP


# ── The spec and the code do not drift ──────────────────────────────────────


def test_doc_consistency_check_passes() -> None:
    """`scripts/check_mqs_doc_consistency.py` is the CI guard that the spec
    and the code agree; run it here so the spec-compliance suite fails loudly
    on any drift, not only the dedicated CI step."""
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "check_mqs_doc_consistency.py"
    assert script.exists(), f"missing consistency check: {script}"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"MQS doc/code drift:\n{result.stdout}\n{result.stderr}"
    )
