"""Trace-coverage tests — Round 17 / prompt 44 follow-up.

Prompt 44 introduced span-based observability; prompts 45-50 added new
code paths that had to be instrumented after the fact. These tests pin
the contract:

1. The ``traced`` decorator emits one span per (sampled) invocation,
   names it sensibly, and stamps the source location.
2. Errors raised inside a traced function are attributed on the span.
3. The ``sample_rate`` parameter is honoured exactly (deterministic
   stride sampling — not a coin flip).
4. The Round 17 entry points (MQS scorer, method linker, lineage
   assembler, citation-chain validator) emit spans under a synthetic
   workload.
5. ``external_api.external_call`` records provider/route/status/retry
   attributes, attributes errors, and never leaks credentials.
6. ``scripts/survey_trace_coverage.py`` correctly classifies traced vs
   untraced public functions.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from noosphere.observability import (
    SpanRecorder,
    SpanStatus,
    set_recorder,
    start_trace,
    traced,
)
from noosphere.observability.external_api import (
    PROVIDER_OPENAI,
    PROVIDER_VOYAGE,
    external_call,
    traced_request,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import survey_trace_coverage as survey_mod  # noqa: E402


@pytest.fixture
def recorder(tmp_path) -> SpanRecorder:
    rec = SpanRecorder(jsonl_path=tmp_path / "spans.jsonl")
    set_recorder(rec)
    yield rec
    set_recorder(None)


def _names(rec: SpanRecorder) -> list[str]:
    return [s.name for s in rec.spans()]


# ── 1. traced decorator mechanics ───────────────────────────────────────────


def test_traced_emits_one_span_per_call(recorder: SpanRecorder) -> None:
    @traced("test.unit_op")
    def op(x: int) -> int:
        return x * 2

    assert op(3) == 6
    assert op(4) == 8
    spans = recorder.spans()
    assert [s.name for s in spans] == ["test.unit_op", "test.unit_op"]
    # Source location is stamped so the trace UI can link back to it.
    assert spans[0].attrs["code.filepath"].endswith("test_trace_coverage.py")
    assert isinstance(spans[0].attrs["code.lineno"], int)


def test_traced_bare_uses_default_span_name(recorder: SpanRecorder) -> None:
    @traced
    def bare_op() -> str:
        return "ok"

    bare_op()
    name = recorder.spans()[0].name
    assert name.endswith("bare_op")
    assert "test_trace_coverage" in name


def test_traced_preserves_wrapped_metadata(recorder: SpanRecorder) -> None:
    @traced("test.documented")
    def documented() -> None:
        """A docstring that must survive wrapping."""

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "A docstring that must survive wrapping."
    assert documented.__traced__ is True
    assert documented.__traced_span_name__ == "test.documented"
    assert documented.__traced_sample_rate__ == 1.0


def test_traced_records_error_attribution(recorder: SpanRecorder) -> None:
    @traced("test.flaky")
    def flaky() -> None:
        raise ValueError("planted failure")

    with pytest.raises(ValueError):
        flaky()

    span = recorder.spans()[0]
    assert span.status == SpanStatus.ERROR
    assert span.error_kind == "ValueError"
    assert "planted failure" in (span.error_message or "")


def test_traced_async_function(recorder: SpanRecorder) -> None:
    @traced("test.async_op")
    async def async_op(x: int) -> int:
        await asyncio.sleep(0)
        return x + 1

    assert asyncio.run(async_op(41)) == 42
    assert _names(recorder) == ["test.async_op"]


# ── 2. Sampling ─────────────────────────────────────────────────────────────


def test_sampling_rate_honoured_exactly(recorder: SpanRecorder) -> None:
    """Deterministic stride sampling: a multiple-of-stride call count
    yields an exact span count regardless of the counter's start phase."""

    @traced("test.hot", sample_rate=0.1)
    def hot() -> None:
        return None

    # 0.1 → stride 10. 50 calls = exactly 5 sampled spans, phase-independent.
    for _ in range(50):
        hot()
    assert len(recorder.spans()) == 5


def test_sampling_rate_zero_emits_nothing(recorder: SpanRecorder) -> None:
    @traced("test.never", sample_rate=0.0)
    def never() -> int:
        return 7

    for _ in range(20):
        assert never() == 7  # still runs
    assert recorder.spans() == []


def test_sampled_out_calls_still_execute(recorder: SpanRecorder) -> None:
    calls: list[int] = []

    @traced("test.counted", sample_rate=0.1)
    def counted() -> None:
        calls.append(1)

    for _ in range(10):
        counted()
    assert len(calls) == 10  # every call ran
    assert len(recorder.spans()) == 1  # only one was traced


# ── 3. Round 17 entry points emit spans under a synthetic workload ─────────


def test_mqs_scorer_emits_spans(recorder: SpanRecorder) -> None:
    from noosphere.evaluation.mqs import MqsInput, score_conclusion

    # composite_score is sampled at 0.05 (stride 20); 20 score_conclusion
    # calls is one full stride window → exactly one composite span.
    for i in range(20):
        score_conclusion(MqsInput(conclusion_id=f"c{i}", conclusion_text="x"))

    names = set(_names(recorder))
    for expected in (
        "mqs.score_conclusion",
        "mqs.score_progressivity",
        "mqs.score_severity",
        "mqs.score_aim_method_fit",
        "mqs.score_compressibility",
        "mqs.score_domain_sensitivity",
        "mqs.composite_score",
    ):
        assert expected in names, f"missing span: {expected}"

    # Sub-scorers nest under the score_conclusion span — same trace.
    trace_ids = {s.trace_id for s in recorder.spans()}
    assert len(trace_ids) == 20  # one trace per top-level score_conclusion


def test_method_outcome_linker_emits_spans(recorder: SpanRecorder) -> None:
    from noosphere.evaluation.method_outcome_linker import (
        RegistryMethodView,
        StubMethodLinkerJudge,
        infer_links,
        upsert_links,
    )
    from noosphere.evaluation.mqs import MethodologyProfileSummary

    links = infer_links(
        conclusion_id="c1",
        conclusion_text="t",
        topic_hint="energy",
        profiles=[MethodologyProfileSummary(pattern_type="m", confidence=0.7)],
        registry_methods=[RegistryMethodView(name="m", version="1")],
        judge=StubMethodLinkerJudge(),
    )

    class _FakeCursor:
        def __init__(self) -> None:
            self.rows = 0

        def execute(self, *_args, **_kwargs) -> None:
            self.rows += 1

    upsert_links(
        _FakeCursor(),
        organization_id="org",
        conclusion_id="c1",
        links=links,
    )

    names = set(_names(recorder))
    assert "method_outcome_linker.infer_links" in names
    assert "method_outcome_linker.upsert_links" in names


def test_citation_chain_emits_spans(recorder: SpanRecorder) -> None:
    from noosphere.literature.citation_chain import (
        CitationCandidate,
        CitationRelation,
        InMemoryCitationVerdictLedger,
        NLIJudgment,
        apply_override,
        triage_payloads,
        validate_citations,
    )

    def judge(_premise: str, _hypothesis: str) -> NLIJudgment:
        return NLIJudgment(entailment=0.9, neutral=0.05, contradiction=0.05)

    candidates = [
        CitationCandidate(
            citation_kind="opinion",
            citation_id=f"cite{i}",
            source_id="src",
            stated_claim="the firm's claim",
            source_text="a windowed excerpt of the source text " * 5,
            relation=CitationRelation.SUPPORTS,
        )
        for i in range(20)
    ]
    verdicts = validate_citations(candidates, judge, InMemoryCitationVerdictLedger())
    triage_payloads(verdicts)
    apply_override(verdicts[0], overridden_by="founder", override_reason="reviewed")

    names = set(_names(recorder))
    for expected in (
        "citation_chain.validate_citations",
        "citation_chain.judge_citation",  # sampled 0.1 → present at 20 calls
        "citation_chain.extract_excerpt",  # sampled 0.05 → present at 20 calls
        "citation_chain.triage_payloads",
        "citation_chain.apply_override",
    ):
        assert expected in names, f"missing span: {expected}"


def test_lineage_emits_spans(recorder: SpanRecorder) -> None:
    from noosphere.temporal.lineage import (
        Lineage,
        LineageNode,
        LineageNodeKind,
        assemble_lineage,
        lineage_diff,
        lineage_source_ids,
        lineage_to_markdown,
    )

    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    node = LineageNode(
        id="source:s1",
        kind=LineageNodeKind.SOURCE,
        label="a source",
        timestamp=now,
        public_visible=True,
    )
    lin = Lineage(conclusion_id="c1", assembled_at=now, nodes=[node], edges=[])

    lineage_to_markdown(lin)
    lineage_source_ids(lin)
    lineage_diff(lin, lin)

    # assemble_lineage walks a Store; a minimal fake exercises the span
    # without standing up a database.
    conclusion = SimpleNamespace(
        id="c1",
        text="conclusion text",
        rationale="why",
        reasoning="",
        confidence=0.8,
        confidence_tier=SimpleNamespace(value="exploratory"),
        created_at=now,
        evidence_chain_claim_ids=[],
        dissent_claim_ids=[],
    )

    class _FakeStore:
        def get_conclusion(self, _cid: str):
            return conclusion

        def iter_cascade_edges(self, *, dst: str):  # noqa: ARG002
            return []

        def list_review_reports(self, _cid: str):
            return []

        def list_drift_events(self):
            return []

    assemble_lineage(_FakeStore(), "c1")

    names = set(_names(recorder))
    for expected in (
        "lineage.assemble_lineage",
        "lineage.lineage_diff",
        "lineage.lineage_to_markdown",
        "lineage.lineage_source_ids",
    ):
        assert expected in names, f"missing span: {expected}"


# ── 4. External API instrumentation ─────────────────────────────────────────


def test_external_call_records_request_metadata(recorder: SpanRecorder) -> None:
    with external_call(
        PROVIDER_OPENAI, route="/v1/chat/completions", model="gpt-4o"
    ) as call:
        call.set_status_code(200)
        call.set_attr("prompt_tokens", 1200)

    span = recorder.spans()[0]
    assert span.name == "external.openai"
    assert span.status == SpanStatus.OK
    assert span.attrs["provider"] == "openai"
    assert span.attrs["route"] == "/v1/chat/completions"
    assert span.attrs["model"] == "gpt-4o"
    assert span.attrs["status_code"] == 200
    assert span.attrs["retry_count"] == 0
    assert "latency_ms" in span.attrs


def test_external_call_records_retries_and_errors(recorder: SpanRecorder) -> None:
    with pytest.raises(RuntimeError):
        with external_call(PROVIDER_VOYAGE, route="/v1/embeddings") as call:
            call.record_retry()
            call.record_retry()
            call.set_status_code(503)
            raise RuntimeError("upstream 503")

    span = recorder.spans()[0]
    assert span.status == SpanStatus.ERROR
    assert span.error_kind == "RuntimeError"
    assert "upstream 503" in (span.error_message or "")
    assert span.attrs["retry_count"] == 2
    assert span.attrs["status_code"] == 503


def test_external_call_does_not_leak_credentials(recorder: SpanRecorder) -> None:
    """Span privacy: even if a caller is careless and hands the wrapper a
    key-shaped attr, the sanitizer must redact it before persistence."""
    with external_call(
        PROVIDER_OPENAI,
        route="/v1/messages",
        attrs={"api_key": "sk-supersecrettoken1234567", "region": "us-east"},
    ) as call:
        call.set_attr("authorization", "Bearer tok_abcdef123456")

    span = recorder.spans()[0]
    assert span.attrs["api_key"] == "[redacted]"
    assert span.attrs["authorization"] == "[redacted]"
    assert span.attrs["region"] == "us-east"  # structural metadata survives


def test_traced_request_counts_retries(recorder: SpanRecorder) -> None:
    attempts = {"n": 0}

    def flaky_request() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("transient")
        return "body"

    result = traced_request(
        PROVIDER_VOYAGE,
        route="/v1/embeddings",
        request=flaky_request,
        max_retries=5,
        retry_on=(ConnectionError,),
        status_of=lambda _body: 200,
    )
    assert result == "body"
    span = recorder.spans()[0]
    assert span.attrs["retry_count"] == 2
    assert span.attrs["status_code"] == 200
    assert span.status == SpanStatus.OK


def test_traced_request_reraises_after_exhausting_retries(
    recorder: SpanRecorder,
) -> None:
    def always_fails() -> str:
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        traced_request(
            PROVIDER_VOYAGE,
            route="/v1/embeddings",
            request=always_fails,
            max_retries=2,
            retry_on=(ConnectionError,),
        )
    span = recorder.spans()[0]
    assert span.status == SpanStatus.ERROR
    assert span.attrs["retry_count"] == 2


# ── 5. The survey script ────────────────────────────────────────────────────


def test_survey_classifies_traced_and_untraced() -> None:
    results = survey_mod.survey()
    by_qualname = {
        (r.package, r.qualname): r
        for records in results.values()
        for r in records
    }

    # score_conclusion was wrapped by the auto-wrap pass.
    sc = by_qualname[("inquiry → evaluation", "score_conclusion")]
    assert sc.is_traced is True
    assert sc.span_name == "mqs.score_conclusion"

    # composite_score carries the hot-path sample rate.
    cs = by_qualname[("inquiry → evaluation", "composite_score")]
    assert cs.is_traced is True
    assert cs.sample_rate == pytest.approx(0.05)

    # evidence_payload is a pure serializer — intentionally NOT traced,
    # and the survey must report it as a gap.
    ep = by_qualname[("inquiry → evaluation", "evidence_payload")]
    assert ep.is_traced is False
    assert ep.sample_rate is None


def test_survey_renders_markdown_with_gap_section() -> None:
    results = survey_mod.survey()
    md = survey_mod.render_markdown(results)
    assert "# Trace Coverage" in md
    assert "## Summary" in md
    assert "Public functions surveyed" in md
    # There are known un-instrumented helpers, so the gap section must render.
    assert "NOT wrapped by `@traced`" in md
    # Traced span names surface in the per-package tables.
    assert "mqs.score_conclusion" in md


def test_survey_check_mode_flags_gaps() -> None:
    """``--check`` exits non-zero while gaps remain — the CI gate."""
    rc = survey_mod.main(["--check", "--stdout"])
    assert rc == 1


def test_survey_detects_scoped_entry_points_are_traced() -> None:
    """Every public function in the four files the prompt scoped for the
    auto-wrap pass is instrumented (modulo intentional pure-helper skips)."""
    results = survey_mod.survey()
    flat = [r for records in results.values() for r in records]

    scoped_traced = {
        "mqs.py": {
            "score_conclusion",
            "score_progressivity",
            "score_severity",
            "score_aim_method_fit",
            "score_compressibility",
            "score_domain_sensitivity",
            "composite_score",
        },
        "method_outcome_linker.py": {
            "infer_links",
            "registry_view",
            "upsert_links",
        },
        "lineage.py": {
            "assemble_lineage",
            "lineage_diff",
            "lineage_to_markdown",
            "lineage_source_ids",
        },
        "citation_chain.py": {
            "validate_citations",
            "judge_citation",
            "extract_excerpt",
            "triage_payloads",
            "apply_override",
            "revalidate_for_source",
            "revalidate_on_standing_change",
        },
    }
    for filename, expected in scoped_traced.items():
        traced_here = {
            r.qualname
            for r in flat
            if r.module.endswith(filename[:-3]) and r.is_traced
        }
        missing = expected - traced_here
        assert not missing, f"{filename}: expected traced but weren't: {missing}"
