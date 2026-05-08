"""Unit tests for the load runner's parsing and aggregation.

These tests exist because the harness's pass/fail signal blocks
deploys: a bug in percentile math could either green-light a degraded
deploy or block a healthy one. We don't load-test in unit tests — we
feed synthetic ``RequestResult`` lists through ``aggregate`` and
``evaluate``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from lib import runner  # noqa: E402


def _ok(path: str, ms: float) -> runner.RequestResult:
    return runner.RequestResult(path=path, status=200, duration_ms=ms)


def _err(path: str, status: int = 500) -> runner.RequestResult:
    return runner.RequestResult(
        path=path,
        status=status,
        duration_ms=10.0,
        error=f"HTTP {status}",
    )


def test_aggregate_empty():
    stats = runner.aggregate([])
    assert stats.total == 0
    assert stats.error_rate == 0.0
    assert stats.p50_ms == 0.0


def test_aggregate_percentiles_simple():
    rows = [_ok("/", float(i)) for i in range(1, 101)]
    stats = runner.aggregate(rows)
    assert stats.total == 100
    assert stats.errors == 0
    assert stats.p50_ms == 50
    assert stats.p95_ms == 95
    assert stats.p99_ms == 99


def test_aggregate_marks_5xx_and_network_errors():
    rows = [_ok("/", 100.0), _err("/", 500), _err("/", 503)]
    rows.append(
        runner.RequestResult(
            path="/api/public/ask",
            status=0,
            duration_ms=5.0,
            error="URLError",
        ),
    )
    stats = runner.aggregate(rows)
    assert stats.total == 4
    assert stats.errors == 3
    assert stats.error_rate == 0.75


def test_aggregate_per_path_buckets():
    rows = [
        _ok("/", 50.0),
        _ok("/", 150.0),
        _ok("/api/public/ask", 200.0),
        _err("/api/public/ask", 500),
    ]
    stats = runner.aggregate(rows)
    assert stats.by_path["/"]["count"] == 2
    assert stats.by_path["/"]["errors"] == 0
    assert stats.by_path["/api/public/ask"]["count"] == 2
    assert stats.by_path["/api/public/ask"]["errors"] == 1


def test_pool_exhaustion_detection_via_body_sample():
    body = b"FATAL: remaining connection slots are reserved"
    assert runner._looks_like_pool_exhaustion(503, body) is True
    assert runner._looks_like_pool_exhaustion(503, b"oops") is False
    assert runner._looks_like_pool_exhaustion(404, body) is False


def test_evaluate_passes_within_budget():
    stats = runner.RunStats(
        total=100,
        errors=0,
        error_rate=0.0,
        p50_ms=200.0,
        p95_ms=900.0,
        p99_ms=1500.0,
        pool_exhaustion_events=0,
    )
    budget = runner.Budget(
        p50_ms=1000.0, p95_ms=3000.0, error_rate=0.01,
    )
    verdict = runner.evaluate(stats, budget)
    assert verdict.passed is True
    assert verdict.reasons == []


def test_evaluate_collects_all_violations():
    stats = runner.RunStats(
        total=100,
        errors=5,
        error_rate=0.05,
        p50_ms=1500.0,
        p95_ms=4000.0,
        p99_ms=5000.0,
        pool_exhaustion_events=2,
    )
    budget = runner.Budget(
        p50_ms=1000.0, p95_ms=3000.0, error_rate=0.01,
        max_pool_exhaustion_events=0,
    )
    verdict = runner.evaluate(stats, budget)
    assert verdict.passed is False
    assert len(verdict.reasons) == 4
    assert any("p50" in r for r in verdict.reasons)
    assert any("p95" in r for r in verdict.reasons)
    assert any("error rate" in r for r in verdict.reasons)
    assert any("pool-exhaustion" in r for r in verdict.reasons)


def test_load_profile_parses_known_profiles(tmp_path: Path):
    target = tmp_path / "profiles.json"
    target.write_text(
        json.dumps(
            {
                "profiles": {
                    "viral": {
                        "concurrency": 200,
                        "peak_concurrency": 200,
                        "ramp_seconds": 15,
                        "duration_seconds": 120,
                        "budget": {
                            "p50_ms": 1000,
                            "p95_ms": 3000,
                            "error_rate": 0.01,
                            "max_pool_exhaustion_events": 0,
                        },
                    }
                }
            }
        )
    )
    profile = runner.load_profile("viral", target)
    assert profile.name == "viral"
    assert profile.concurrency == 200
    assert profile.budget.p50_ms == 1000


def test_load_profile_rejects_unknown(tmp_path: Path):
    target = tmp_path / "profiles.json"
    target.write_text(json.dumps({"profiles": {}}))
    with pytest.raises(KeyError):
        runner.load_profile("does-not-exist", target)


def test_session_paths_includes_post_and_ask():
    plan = runner.session_paths("my-slug", "concl-1")
    methods = [m for m, _, _ in plan]
    paths = [p for _, p, _ in plan]
    assert "GET" in methods and "POST" in methods
    assert "/post/my-slug" in paths
    assert "/api/public/conclusion/concl-1/lineage" in paths
    assert "/api/public/methodology/manifest" in paths
    assert "/api/public/ask" in paths
    # Critical: never any third-party host.
    for _, path, _ in plan:
        assert path.startswith("/")


def test_session_paths_omits_lineage_when_no_id():
    plan = runner.session_paths("slug", None)
    paths = [p for _, p, _ in plan]
    assert all("lineage" not in p for p in paths)


def test_session_paths_skips_third_party_targets():
    """Regression: if anyone adds Polymarket/Kalshi/OpenAI URLs to the
    plan, this test fails. The harness MUST NOT load-test third-party
    APIs.
    """
    plan = runner.session_paths("slug", "id")
    forbidden = ("polymarket", "kalshi", "openai", "anthropic", "://")
    for _, path, _ in plan:
        for hint in forbidden:
            assert hint not in path.lower()


def test_synthetic_user_agent_format():
    ua = runner.synthetic_user_agent("viral", "abcdef")
    assert ua.startswith(runner.SYNTHETIC_USER_AGENT_PREFIX + "/")
    assert "viral" in ua
    assert "abcdef" in ua


def test_simulate_session_uses_synthetic_ua_and_walks_plan():
    seen: list[tuple[str, str, str | None]] = []

    def fake_request(base_url, path, user_agent, method="GET", body=None, timeout=10.0):
        seen.append((method, path, user_agent))
        return runner.RequestResult(path=path, status=200, duration_ms=1.0)

    out = runner.simulate_session(
        base_url="http://test",
        user_agent="theseus-loadtest/light/run1",
        article_slug="hello",
        conclusion_id=None,
        request_fn=fake_request,
        jitter_ms=(0, 0),
    )
    assert len(out) == len(seen)
    assert all(ua == "theseus-loadtest/light/run1" for _, _, ua in seen)


def test_report_to_json_round_trip():
    stats = runner.RunStats(
        total=10,
        errors=0,
        error_rate=0.0,
        p50_ms=100.0,
        p95_ms=200.0,
        p99_ms=300.0,
        pool_exhaustion_events=0,
        by_path={"/": {"count": 10, "errors": 0, "p50_ms": 100, "p95_ms": 200}},
    )
    budget = runner.Budget(p50_ms=1000.0, p95_ms=3000.0, error_rate=0.01)
    verdict = runner.Verdict(passed=True, reasons=[])
    report = runner.RunReport(
        profile="light",
        started_at="2026-05-08T00:00:00+00:00",
        finished_at="2026-05-08T00:00:30+00:00",
        base_url="http://test",
        article_slug="hello",
        stats=stats,
        budget=budget,
        verdict=verdict,
        samples=10,
    )
    blob = runner.report_to_json(report)
    # The shape consumed by loadTestData.ts:
    assert blob["profile"] == "light"
    assert blob["stats"]["p50Ms"] == 100.0
    assert blob["stats"]["errorRate"] == 0.0
    assert blob["budget"]["p50_ms"] == 1000.0
    assert blob["verdict"]["passed"] is True
    # Must be JSON-serializable.
    json.dumps(blob)


def test_ramp_concurrency_linear_then_holds():
    profile = runner.LoadProfile(
        name="spike",
        concurrency=200,
        peak_concurrency=500,
        ramp_seconds=30,
        duration_seconds=90,
        budget=runner.Budget(p50_ms=1000, p95_ms=3000, error_rate=0.01),
    )
    assert runner._ramp_concurrency(profile, 0) == 200
    assert runner._ramp_concurrency(profile, 15) == 350
    assert runner._ramp_concurrency(profile, 30) == 500
    assert runner._ramp_concurrency(profile, 60) == 500


def test_ramp_concurrency_flat_when_peak_equals_base():
    profile = runner.LoadProfile(
        name="viral",
        concurrency=200,
        peak_concurrency=200,
        ramp_seconds=15,
        duration_seconds=120,
        budget=runner.Budget(p50_ms=1000, p95_ms=3000, error_rate=0.01),
    )
    assert runner._ramp_concurrency(profile, 0) == 200
    assert runner._ramp_concurrency(profile, 200) == 200


def test_real_profiles_json_matches_spec():
    """Sanity check on the tracked profiles file. If you tighten or
    loosen a budget you should also update the dashboard's headline
    description.
    """
    profiles_path = _HERE / "profiles.json"
    light = runner.load_profile("light", profiles_path)
    viral = runner.load_profile("viral", profiles_path)
    spike = runner.load_profile("spike", profiles_path)
    assert light.concurrency == 50
    assert viral.concurrency == 200
    assert spike.peak_concurrency == 500
    assert spike.ramp_seconds <= 30
    for profile in (light, viral, spike):
        assert profile.budget.p50_ms == 1000
        assert profile.budget.p95_ms == 3000
        assert profile.budget.error_rate == 0.01
