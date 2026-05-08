"""Methodology version diff + effect-on-results tests.

Two synthetic versions of a stub method, one conclusion analyzed under
each. The tests assert:

* Hash stability: same content → same hash, line-ending-only changes do
  not change the hash, irrelevant trailing whitespace is normalized.
* Diff render: code, rationale, failures (adds / removes / changes),
  and domain-bound diffs are produced by ``render_diff``.
* Public-vs-private visibility: private failure modes do not appear in
  the public diff.
* Effect report: only conclusions analyzed under both versions are
  counted; conclusions that exist under only one side appear in
  ``only_in_a`` / ``only_in_b``.
* Anchor URL stability: the anchor is derived from the content hash and
  is therefore identical across renders.
* Digest event: a method version transition produces a ``DigestEvent``
  that flows through ``select_events_for`` for methodology-scope
  subscribers and links to the stable anchor.
"""

from __future__ import annotations

from datetime import datetime, timezone

from noosphere.methods.version_diff import (
    ConclusionAnalysis,
    changelog_anchor,
    effect_on_results,
    render_diff,
)
from noosphere.methods.version_snapshot import (
    InMemoryMethodVersionStore,
    capture_snapshot,
)
from noosphere.social.digest_builder import (
    Subscriber,
    build_method_version_event,
    select_events_for,
)


# ── Stub method content ────────────────────────────────────────────────────

_STUB_NAME = "stub_method_v_diff"

_SOURCE_V1 = '''"""Stub method v1.0.0 — used by tests only."""


def stub_method(payload):
    return {"score": float(payload.get("x", 0)) * 2.0}
'''

_SOURCE_V2 = '''"""Stub method v1.1.0 — used by tests only.

Bug fix: clamp the input so unbounded x can't blow up downstream
calibration.
"""


def stub_method(payload):
    x = max(-1.0, min(1.0, float(payload.get("x", 0))))
    return {"score": x * 2.0}
'''

_RATIONALE_V1 = "Initial stub. Doubles its input for testing."
_RATIONALE_V2 = (
    "Initial stub, now clamped. Doubles its input for testing, but the "
    "input is first clamped to [-1, 1] so synthetic regressions don't "
    "explode the calibration estimator."
)

_FAILURES_V1 = """\
method: stub_method_v_diff
modes:
  - name: unbounded_input
    description: |
      The input can be unbounded. Synthetic regressions explode.
    worked_example: x = 1e9 produced score 2e9.
    trigger_conditions: |
      Any input |x| > 1.
    mitigation: Clamp input.
    severity: high
    citations: []
    public: true
  - name: nan_input
    description: |
      NaN input is forwarded silently. Downstream calibration is
      then NaN.
    worked_example: x = NaN produced score NaN.
    trigger_conditions: |
      math.isnan(x).
    mitigation: Reject NaN at input.
    severity: medium
    citations: []
    public: false
"""

_FAILURES_V2 = """\
method: stub_method_v_diff
modes:
  - name: nan_input
    description: |
      NaN input is forwarded silently. Downstream calibration is
      then NaN.
    worked_example: x = NaN produced score NaN.
    trigger_conditions: |
      math.isnan(x).
    mitigation: Reject NaN at input.
    severity: medium
    citations: []
    public: false
  - name: clamp_obscures_outlier
    description: |
      Clamping to [-1, 1] hides outlier pressure from monitoring. The
      method's "everything fine" output looks identical for x = 2 and
      x = 1e9.
    worked_example: x = 1e9 and x = 2 both produced score 2.0.
    trigger_conditions: |
      |x| > 1 in production traffic.
    mitigation: Emit a clamp counter to the operator dashboard.
    severity: medium
    citations: []
    public: true
"""

_DOMAIN_V1 = ""
_DOMAIN_V2 = '{"combinator": "any", "tags": ["unit_test"]}'


def _capture(version: str, *, source, rationale, failures, domain):
    return capture_snapshot(
        _STUB_NAME,
        version,
        source_override=source,
        rationale_override=rationale,
        failures_override=failures,
        domain_bound_override=domain,
    )


def _v1():
    return _capture(
        "1.0.0",
        source=_SOURCE_V1,
        rationale=_RATIONALE_V1,
        failures=_FAILURES_V1,
        domain=_DOMAIN_V1,
    )


def _v2():
    return _capture(
        "1.1.0",
        source=_SOURCE_V2,
        rationale=_RATIONALE_V2,
        failures=_FAILURES_V2,
        domain=_DOMAIN_V2,
    )


# ── Hash stability ─────────────────────────────────────────────────────────


def test_hash_is_stable_across_line_endings_and_trailing_whitespace():
    a = _capture(
        "1.0.0",
        source=_SOURCE_V1,
        rationale=_RATIONALE_V1,
        failures=_FAILURES_V1,
        domain=_DOMAIN_V1,
    )
    crlf_source = _SOURCE_V1.replace("\n", "\r\n") + "   \n"
    trailing_rationale = _RATIONALE_V1 + "    \n\n\n"
    b = _capture(
        "1.0.0",
        source=crlf_source,
        rationale=trailing_rationale,
        failures=_FAILURES_V1,
        domain=_DOMAIN_V1,
    )
    assert a.content_hash == b.content_hash
    # And a real change moves the hash:
    c = _v2()
    assert a.content_hash != c.content_hash


def test_in_memory_store_round_trip():
    store = InMemoryMethodVersionStore()
    a = _v1()
    b = _v2()
    store.upsert(a)
    store.upsert(b)
    assert store.get(_STUB_NAME, "1.0.0").content_hash == a.content_hash
    assert store.get_by_hash(b.content_hash).version == "1.1.0"
    snapshots = store.list_for(_STUB_NAME)
    assert [s.version for s in snapshots] == ["1.0.0", "1.1.0"]
    # Re-upserting the same hash is idempotent.
    store.upsert(_v1())
    assert len(store.list_for(_STUB_NAME)) == 2


# ── Diff render ────────────────────────────────────────────────────────────


def test_render_diff_covers_code_rationale_failures_and_domain():
    diff = render_diff(_v1(), _v2(), visibility="private")
    assert diff.name == _STUB_NAME
    assert diff.code_diff and "clamp" in diff.code_diff
    assert diff.rationale_diff and "clamped" in diff.rationale_diff
    assert "clamp_obscures_outlier" in diff.failures_delta.added
    assert "unbounded_input" in diff.failures_delta.removed
    assert "nan_input" not in diff.failures_delta.changed
    assert diff.domain_bound_diff and "unit_test" in diff.domain_bound_diff
    assert not diff.is_empty()


def test_public_diff_hides_private_failure_modes():
    # "nan_input" is public:false on both sides; it must never appear
    # in the public diff regardless of whether it is added, removed,
    # or changed under the hood.
    diff_public = render_diff(_v1(), _v2(), visibility="public")
    assert "nan_input" not in diff_public.failures_delta.added
    assert "nan_input" not in diff_public.failures_delta.removed
    assert "nan_input" not in diff_public.failures_delta.changed
    assert "clamp_obscures_outlier" in diff_public.failures_delta.added
    assert "unbounded_input" in diff_public.failures_delta.removed


def test_render_diff_identical_snapshots_is_empty():
    a = _v1()
    b = _v1()
    diff = render_diff(a, b)
    assert diff.is_empty()


# ── Effect-on-results report ───────────────────────────────────────────────


def test_effect_on_results_counts_only_reanalyzed_conclusions():
    a = _v1()
    b = _v2()

    analyses = [
        # Conclusion C1 was analyzed under both versions — counted.
        ConclusionAnalysis(
            conclusion_id="c1",
            method_version_hash=a.content_hash,
            mqs_sub_scores={"severity": 0.4, "calibration": 0.6},
            calibration_metric=0.30,
        ),
        ConclusionAnalysis(
            conclusion_id="c1",
            method_version_hash=b.content_hash,
            mqs_sub_scores={"severity": 0.5, "calibration": 0.7},
            calibration_metric=0.22,
        ),
        # Conclusion C2 is only under v1 → only_in_a.
        ConclusionAnalysis(
            conclusion_id="c2",
            method_version_hash=a.content_hash,
            mqs_sub_scores={"severity": 0.7, "calibration": 0.5},
            calibration_metric=0.40,
        ),
        # Conclusion C3 is only under v2 → only_in_b.
        ConclusionAnalysis(
            conclusion_id="c3",
            method_version_hash=b.content_hash,
            mqs_sub_scores={"severity": 0.8, "calibration": 0.4},
            calibration_metric=0.31,
        ),
    ]

    report = effect_on_results(a, b, analyses)
    assert report.conclusion_count() == 1
    assert report.only_in_a == ("c2",)
    assert report.only_in_b == ("c3",)

    only_effect = report.reanalyzed[0]
    assert only_effect.conclusion_id == "c1"
    assert abs(only_effect.mqs_deltas["severity"] - 0.1) < 1e-9
    assert abs(only_effect.mqs_deltas["calibration"] - 0.1) < 1e-9
    # Calibration metric improved (Brier dropped).
    assert only_effect.calibration_delta is not None
    assert only_effect.calibration_delta < 0.0

    # Means are computed over the re-analyzed set only.
    assert abs(report.mean_mqs_deltas["severity"] - 0.1) < 1e-9
    assert report.mean_calibration_delta is not None
    assert report.mean_calibration_delta < 0.0


# ── Anchor URL stability ──────────────────────────────────────────────────


def test_anchor_url_is_stable_and_machine_independent():
    snap1 = _v2()
    snap2 = _v2()
    # Two captures of the same content yield identical anchors.
    assert changelog_anchor(snap1) == changelog_anchor(snap2)
    assert changelog_anchor(snap1).startswith("v-")
    # A different version's anchor differs.
    assert changelog_anchor(snap1) != changelog_anchor(_v1())


# ── Digest hook ────────────────────────────────────────────────────────────


def test_method_version_event_reaches_methodology_scope_subscribers():
    snap = _v2()
    event = build_method_version_event(
        method_name=_STUB_NAME,
        from_version="1.0.0",
        to_version="1.1.0",
        anchor_id=changelog_anchor(snap),
        site_url="https://example.test",
        occurred_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    assert event.kind == "method_version"
    assert event.url.endswith(f"#{changelog_anchor(snap)}")
    assert _STUB_NAME in event.methodology_names

    # Methodology-scope subscriber receives it; firm-scope also; an
    # unrelated methodology subscriber does not.
    methodology_sub = Subscriber(
        id="s1",
        email="a@example.test",
        scope="methodology",
        scope_key=_STUB_NAME,
        cadence="weekly",
        unsubscribe_token="t1",
    )
    other_sub = Subscriber(
        id="s2",
        email="b@example.test",
        scope="methodology",
        scope_key="some_other_method",
        cadence="weekly",
        unsubscribe_token="t2",
    )
    firm_sub = Subscriber(
        id="s3",
        email="c@example.test",
        scope="firm",
        scope_key="",
        cadence="weekly",
        unsubscribe_token="t3",
    )
    now = datetime(2026, 5, 2, tzinfo=timezone.utc)
    assert select_events_for(methodology_sub, [event], now) == [event]
    assert select_events_for(other_sub, [event], now) == []
    assert select_events_for(firm_sub, [event], now) == [event]
