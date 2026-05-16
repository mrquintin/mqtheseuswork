"""Tests for the env validation registry + report.

Covers the contract surface that the boot check, the CLI, the
operator docs, and the credential validator all consume.
"""

from __future__ import annotations

import math

import pytest

from noosphere.core.env_validation import (
    Mode,
    REGISTRY,
    Status,
    VarType,
    parse_mode,
    registry_lookup,
    required_vars_for_mode,
    validate_env,
)


def _complete_env(mode: Mode) -> dict[str, str]:
    """Build a stand-in env that satisfies every required var in ``mode``."""
    env: dict[str, str] = {}
    for req in REGISTRY:
        if not req.is_required(mode):
            continue
        if req.type == VarType.SECRET:
            env[req.var_name] = "secret-test-value-do-not-leak"
        elif req.type == VarType.STRING:
            env[req.var_name] = "ok"
        elif req.type == VarType.ENUM:
            env[req.var_name] = (req.enum_values or ("HUMAN",))[0]
        elif req.type == VarType.BOOLEAN:
            env[req.var_name] = "false"
        else:  # NUMBER / DURATION
            if req.range is not None:
                lo, hi = req.range
                mid = lo + (hi - lo) / 2 if hi > lo else lo
                env[req.var_name] = str(mid)
            else:
                env[req.var_name] = "1"
    return env


def test_pass_on_complete_env() -> None:
    env = _complete_env(Mode.ALGORITHMS_ONLY)
    report = validate_env(Mode.ALGORITHMS_ONLY, env=env)
    assert report.ok(), report.to_dict()
    failures = report.failures()
    assert failures == ()


def test_pass_on_full_env() -> None:
    env = _complete_env(Mode.FULL)
    report = validate_env(Mode.FULL, env=env)
    assert report.ok(), [(r.var_name, r.status.value, r.message) for r in report.failures()]


def test_missing_required_var_reports_missing() -> None:
    env = _complete_env(Mode.ALGORITHMS_ONLY)
    env.pop("DATABASE_URL", None)
    env.pop("ANTHROPIC_API_KEY", None)
    report = validate_env(Mode.ALGORITHMS_ONLY, env=env)
    failed = {r.var_name: r for r in report.failures()}
    assert "DATABASE_URL" in failed
    assert failed["DATABASE_URL"].status == Status.MISSING
    assert "ANTHROPIC_API_KEY" in failed
    assert failed["ANTHROPIC_API_KEY"].status == Status.MISSING


def test_out_of_range_negative() -> None:
    env = _complete_env(Mode.ALGORITHMS_ONLY)
    env["ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS"] = "-1"
    report = validate_env(Mode.ALGORITHMS_ONLY, env=env)
    row = next(r for r in report.rows if r.var_name == "ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS")
    assert row.status == Status.OUT_OF_RANGE


def test_out_of_range_inf_nan() -> None:
    env = _complete_env(Mode.ALGORITHMS_ONLY)
    env["ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS"] = "inf"
    report = validate_env(Mode.ALGORITHMS_ONLY, env=env)
    row = next(r for r in report.rows if r.var_name == "ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS")
    assert row.status == Status.OUT_OF_RANGE

    env["ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS"] = "nan"
    report = validate_env(Mode.ALGORITHMS_ONLY, env=env)
    row = next(r for r in report.rows if r.var_name == "ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS")
    assert row.status == Status.OUT_OF_RANGE


def test_type_mismatch_on_non_numeric() -> None:
    env = _complete_env(Mode.ALGORITHMS_ONLY)
    env["ALGORITHMS_TICK_INTERVAL_S"] = "soonish"
    report = validate_env(Mode.ALGORITHMS_ONLY, env=env)
    row = next(r for r in report.rows if r.var_name == "ALGORITHMS_TICK_INTERVAL_S")
    assert row.status == Status.TYPE_MISMATCH


def test_invalid_enum_reports_off_list() -> None:
    env = _complete_env(Mode.FULL)
    env["MEMO_DISPATCH_DEFAULT_MODE"] = "PARTY_MODE"
    report = validate_env(Mode.FULL, env=env)
    row = next(r for r in report.rows if r.var_name == "MEMO_DISPATCH_DEFAULT_MODE")
    assert row.status == Status.INVALID_ENUM


def test_secret_value_never_returned() -> None:
    env = _complete_env(Mode.ALGORITHMS_ONLY)
    env["DATABASE_URL"] = "postgres://leak-marker-do-not-show:pw@host/db"
    env["ANTHROPIC_API_KEY"] = "sk-ant-leak-marker"
    report = validate_env(Mode.ALGORITHMS_ONLY, env=env)
    payload = report.to_dict()
    blob = repr(payload)
    assert "leak-marker-do-not-show" not in blob
    assert "sk-ant-leak-marker" not in blob
    # And the masked_value column is opaque.
    for row in report.rows:
        if row.var_name in {"DATABASE_URL", "ANTHROPIC_API_KEY"}:
            assert row.masked_value == "***"


def test_optional_missing_is_not_failure() -> None:
    # In algorithms-only mode the live-trading vars are optional and
    # absent in a stripped env — should report OPTIONAL_MISSING, not MISSING.
    env = _complete_env(Mode.ALGORITHMS_ONLY)
    report = validate_env(Mode.ALGORITHMS_ONLY, env=env)
    assert report.ok()
    optional_vars = {r.var_name for r in report.rows if r.status == Status.OPTIONAL_MISSING}
    # POLYMARKET_PRIVATE_KEY is live-trading-only, so optional here.
    assert "POLYMARKET_PRIVATE_KEY" in optional_vars


def test_defaults_used_when_var_absent() -> None:
    # ALGORITHMS_TICK_INTERVAL_S has a documented default of 60. If
    # the env doesn't set it, the report should still PASS because
    # the default is applied.
    env = _complete_env(Mode.ALGORITHMS_ONLY)
    env.pop("ALGORITHMS_TICK_INTERVAL_S", None)
    report = validate_env(Mode.ALGORITHMS_ONLY, env=env)
    row = next(r for r in report.rows if r.var_name == "ALGORITHMS_TICK_INTERVAL_S")
    assert row.status == Status.PASS


def test_parse_mode_accepts_known_modes() -> None:
    assert parse_mode("algorithms-only") == Mode.ALGORITHMS_ONLY
    assert parse_mode("synthesizer") == Mode.SYNTHESIZER
    assert parse_mode("full") == Mode.FULL
    assert parse_mode("live-trading") == Mode.LIVE_TRADING
    assert parse_mode(None) == Mode.ALGORITHMS_ONLY
    assert parse_mode("") == Mode.ALGORITHMS_ONLY


def test_parse_mode_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        parse_mode("paper-only")


def test_required_vars_inclusion_lattice() -> None:
    # Algorithms-only requirements must be a subset of synthesizer
    # requirements, which must be a subset of full, etc.
    algo = set(required_vars_for_mode(Mode.ALGORITHMS_ONLY))
    synth = set(required_vars_for_mode(Mode.SYNTHESIZER))
    full = set(required_vars_for_mode(Mode.FULL))
    live = set(required_vars_for_mode(Mode.LIVE_TRADING))
    assert algo.issubset(synth)
    assert synth.issubset(full)
    assert full.issubset(live)
    # And each step strictly adds at least one var.
    assert algo != synth
    assert synth != full
    assert full != live


def test_registry_lookup() -> None:
    assert registry_lookup("DATABASE_URL") is not None
    assert registry_lookup("DOES_NOT_EXIST") is None


def test_round19_required_vars_present_in_full_mode() -> None:
    required = set(required_vars_for_mode(Mode.FULL))
    # Spot-check the Round 19 vars from the prompt.
    must_include = {
        "ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS",
        "ALGORITHMS_BUDGET_HOURLY_COMPLETION_TOKENS",
        "ALGORITHMS_TICK_INTERVAL_S",
        "ALGORITHMS_MAX_TOKENS_PER_FIRE",
        "SYNTHESIZER_BUDGET_HOURLY_PROMPT_TOKENS",
        "SYNTHESIZER_BUDGET_HOURLY_COMPLETION_TOKENS",
        "CLUSTER_JOIN_THRESHOLD",
        "MIN_CLUSTER_SIZE",
        "CROSS_CLUSTER_SAMPLE_FRACTION",
        "CROSS_CLUSTER_RANDOM_FRACTION",
        "CLUSTER_DRIFT_THRESHOLD",
        "CONTRADICTION_THRESHOLD",
        "DIALECTIC_LIVE_CONTRADICTION_THRESHOLD",
        "DIALECTIC_LIVE_LATENCY_TARGET_S",
        "DIALECTIC_AUDIO_RETENTION_DAYS",
        "GRAPH_REASONER_MAX_TOKENS_PER_EDGE",
        "MEMO_DISPATCH_DEFAULT_MODE",
    }
    missing = must_include - required
    assert not missing, f"Round 19 vars not required in FULL: {missing}"


def test_live_trading_adds_calibration_threshold() -> None:
    required = set(required_vars_for_mode(Mode.LIVE_TRADING))
    assert "AUTO_PAPER_REQUIRES_CALIBRATION_THRESHOLD" in required
