"""End-to-end observability tests.

Covers:

1. Trace propagation across at least three hops (synthetic spans).
2. Method-level metric rollup (the dashboard's read path).
3. Threshold alert firing on a planted error spike.
4. Attribute sanitization — no API keys or emails make it into spans.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest

from noosphere.observability import (
    AlertRule,
    Span,
    SpanRecorder,
    SpanStatus,
    current_span,
    current_trace,
    evaluate_alerts,
    rollup_method_metrics,
    set_recorder,
    start_span,
    start_trace,
)
from noosphere.observability.spans import sanitize_attrs


@pytest.fixture
def recorder(tmp_path) -> SpanRecorder:
    rec = SpanRecorder(jsonl_path=tmp_path / "spans.jsonl")
    set_recorder(rec)
    yield rec
    set_recorder(None)


# ── 1. Trace propagation ────────────────────────────────────────────────────


def test_trace_propagates_across_three_hops(recorder: SpanRecorder) -> None:
    """upload → ingester → claim_extractor → publication: one trace_id.

    The contract: every span recorded inside a parent ``start_trace``
    block shares its ``trace_id``, and ``parent_span_id`` walks back
    cleanly to the root. Without this, the dashboard can't reconstruct
    the upload's path.
    """
    with start_trace("upload") as upload_span:
        with start_span("ingester.parse"):
            with start_span("claim_extractor.extract"):
                with start_span("publication.publish"):
                    # Four hops deep — well past the prompt's "at least three".
                    pass

    spans = recorder.spans()
    assert len(spans) == 4
    trace_ids = {s.trace_id for s in spans}
    assert trace_ids == {upload_span.trace_id}, "all hops must share trace_id"

    # Walk parent chain: every non-root span must have a parent in this trace.
    by_id = {s.span_id: s for s in spans}
    roots = [s for s in spans if s.parent_span_id is None]
    assert len(roots) == 1, "exactly one root span"
    assert roots[0].name == "upload"

    for s in spans:
        if s.parent_span_id is not None:
            assert s.parent_span_id in by_id, f"orphan span: {s.name}"

    # Path from leaf (publication) back to root (upload) hits 4 nodes.
    leaf = next(s for s in spans if s.name == "publication.publish")
    chain = [leaf.name]
    cur = leaf
    while cur.parent_span_id is not None:
        cur = by_id[cur.parent_span_id]
        chain.append(cur.name)
    assert chain == [
        "publication.publish",
        "claim_extractor.extract",
        "ingester.parse",
        "upload",
    ]


def test_trace_id_can_be_supplied_externally(recorder: SpanRecorder) -> None:
    """Founder actions attach to an existing trace via header → ``trace_id`` arg."""
    inbound_trace = "trace_from_upstream_request"

    with start_trace("founder.action", trace_id=inbound_trace):
        with start_span("inner"):
            assert current_trace() == inbound_trace

    spans = recorder.spans()
    assert all(s.trace_id == inbound_trace for s in spans)


def test_contextvars_reset_after_span_exits(recorder: SpanRecorder) -> None:
    assert current_trace() is None
    assert current_span() is None
    with start_trace("root"):
        assert current_trace() is not None
    assert current_trace() is None
    assert current_span() is None


def test_error_in_span_is_recorded(recorder: SpanRecorder) -> None:
    with pytest.raises(ValueError):
        with start_span("flaky_op"):
            raise ValueError("boom")

    spans = recorder.spans()
    assert len(spans) == 1
    assert spans[0].status == SpanStatus.ERROR
    assert spans[0].error_kind == "ValueError"
    assert "boom" in (spans[0].error_message or "")


# ── 2. Dashboard aggregation ────────────────────────────────────────────────


def _planted_span(
    *,
    name: str,
    duration_ms: float,
    status: str = SpanStatus.OK,
    cost_usd: float = 0.0,
    trace_id: str = "trace_synth",
) -> Span:
    start = time.time()
    return Span(
        trace_id=trace_id,
        span_id=f"span_{name}_{duration_ms}",
        parent_span_id=None,
        name=name,
        start=start,
        end=start + duration_ms / 1000.0,
        status=status,
        attrs={"cost_usd": cost_usd} if cost_usd else {},
    )


def test_rollup_aggregates_by_method() -> None:
    """The dashboard reads p50/p95/error_rate/cost from this rollup."""
    spans = [
        _planted_span(name="extract_claims", duration_ms=100, cost_usd=0.001),
        _planted_span(name="extract_claims", duration_ms=200, cost_usd=0.002),
        _planted_span(name="extract_claims", duration_ms=300, cost_usd=0.003),
        _planted_span(
            name="extract_claims",
            duration_ms=5_000,
            status=SpanStatus.ERROR,
        ),
        _planted_span(name="classify", duration_ms=50, cost_usd=0.0005),
    ]

    metrics = rollup_method_metrics(spans)
    by_name = {m.method: m for m in metrics}

    assert by_name["extract_claims"].count == 4
    assert by_name["extract_claims"].error_count == 1
    assert by_name["extract_claims"].error_rate == pytest.approx(0.25)
    # Nearest-rank p50 of [100,200,300,5000] (sorted) → index 1 (200ms-ish).
    assert by_name["extract_claims"].p50_ms <= 300.0
    # p95 picks the slow outlier.
    assert by_name["extract_claims"].p95_ms >= 1000.0
    assert by_name["extract_claims"].cost_usd == pytest.approx(0.006)

    assert by_name["classify"].count == 1
    assert by_name["classify"].error_rate == 0.0


def test_rollup_skips_open_spans() -> None:
    """Open spans (``end is None``) have undefined latency — exclude them."""
    open_span = Span(
        trace_id="t",
        span_id="s",
        parent_span_id=None,
        name="still_running",
        start=time.time(),
        end=None,
    )
    closed = _planted_span(name="closed", duration_ms=100)
    metrics = rollup_method_metrics([open_span, closed])
    assert {m.method for m in metrics} == {"closed"}


# ── 3. Alerting ─────────────────────────────────────────────────────────────


def test_alert_fires_on_planted_error_spike() -> None:
    """5%+ sustained errors → alert. Plant a 50% spike, confirm firing."""
    spans = [_planted_span(name="hot_method", duration_ms=100) for _ in range(5)]
    spans += [
        _planted_span(name="hot_method", duration_ms=100, status=SpanStatus.ERROR)
        for _ in range(5)
    ]
    metrics = rollup_method_metrics(spans)

    rule = AlertRule(
        name="error_rate_5pct",
        metric="error_rate",
        threshold=0.05,
        min_samples=5,
    )
    events = evaluate_alerts(metrics, [rule])
    assert len(events) == 1
    assert events[0].rule_name == "error_rate_5pct"
    assert events[0].method == "hot_method"
    assert events[0].value == pytest.approx(0.5)


def test_alert_does_not_fire_below_threshold() -> None:
    spans = [_planted_span(name="cool_method", duration_ms=100) for _ in range(20)]
    metrics = rollup_method_metrics(spans)
    rule = AlertRule(name="r", metric="error_rate", threshold=0.05, min_samples=5)
    assert evaluate_alerts(metrics, [rule]) == []


def test_alert_respects_min_samples() -> None:
    """A single error at small N must not fire — too noisy."""
    spans = [_planted_span(name="rare", duration_ms=10, status=SpanStatus.ERROR)]
    metrics = rollup_method_metrics(spans)
    rule = AlertRule(name="r", metric="error_rate", threshold=0.05, min_samples=5)
    assert evaluate_alerts(metrics, [rule]) == []


# ── 4. PII / credential sanitization ───────────────────────────────────────


def test_sanitize_redacts_known_keys() -> None:
    cleaned = sanitize_attrs(
        {
            "api_key": "sk-abcd1234efgh5678",
            "Authorization": "Bearer tok_abc",
            "claim_count": 7,
        }
    )
    assert cleaned["api_key"] == "[redacted]"
    assert cleaned["Authorization"] == "[redacted]"
    assert cleaned["claim_count"] == 7


def test_sanitize_redacts_inline_credentials_in_values() -> None:
    cleaned = sanitize_attrs(
        {"prompt": "use sk-abcd1234efgh5678 to authorize"}
    )
    assert "sk-abcd" not in cleaned["prompt"]
    assert "[redacted]" in cleaned["prompt"]


def test_sanitize_redacts_emails() -> None:
    cleaned = sanitize_attrs({"note": "ping me at founder@example.com"})
    assert "founder@example.com" not in cleaned["note"]


def test_recorded_span_attrs_are_sanitized(recorder: SpanRecorder) -> None:
    with start_span(
        "external_api_call",
        attrs={"api_key": "sk-secrettoken1234567", "endpoint": "/v1/x"},
    ):
        pass
    span = recorder.spans()[0]
    assert span.attrs["api_key"] == "[redacted]"
    assert span.attrs["endpoint"] == "/v1/x"


# ── 5. JSONL persistence (sanity) ───────────────────────────────────────────


def test_jsonl_tee_writes_one_line_per_span(tmp_path) -> None:
    path = tmp_path / "spans.jsonl"
    rec = SpanRecorder(jsonl_path=path)
    set_recorder(rec)
    try:
        with start_trace("a"):
            with start_span("b"):
                pass
    finally:
        set_recorder(None)

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    payloads = [json.loads(line) for line in lines]
    # Every line must include the trace correlation keys.
    for p in payloads:
        assert "trace_id" in p
        assert "span_id" in p
        assert "name" in p
