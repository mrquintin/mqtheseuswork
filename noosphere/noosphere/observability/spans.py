"""
Span model and trace propagation for Noosphere.

A Span is the atomic unit of observability: one method invocation, one
cascade traversal, one external API call. Spans nest under a single
``trace_id`` so an upload can be followed all the way through ingest →
classify → distill → publish.

Persistence is pluggable: the default ``SpanRecorder`` keeps spans in
memory and tees a JSONL line to ``~/.theseus/logs/spans.jsonl`` (next to
the existing structured log file). The Postgres-backed dashboard reads
the same rows via the Prisma ``Span`` model — a separate sync writer can
be installed via ``set_recorder`` without touching call sites.

Trace IDs flow via ``contextvars`` so they survive across async hops
without explicit threading. Public endpoints originate a trace via
``start_trace``; founder actions can attach to an existing trace by
passing ``trace_id=...`` into ``start_trace``.
"""

from __future__ import annotations

import contextvars
import dataclasses
import functools
import inspect
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, TypeVar


# ── Status ───────────────────────────────────────────────────────────────────


class SpanStatus:
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"


# ── Span ─────────────────────────────────────────────────────────────────────


@dataclass
class Span:
    """One unit of work. Times are unix epoch seconds (UTC)."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start: float
    end: float | None = None
    status: str = SpanStatus.OK
    attrs: dict[str, Any] = field(default_factory=dict)
    error_kind: str | None = None
    error_message: str | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.end is None:
            return None
        return (self.end - self.start) * 1000.0

    @property
    def is_open(self) -> bool:
        return self.end is None

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["start_iso"] = datetime.fromtimestamp(self.start, tz=timezone.utc).isoformat()
        if self.end is not None:
            d["end_iso"] = datetime.fromtimestamp(self.end, tz=timezone.utc).isoformat()
            d["duration_ms"] = self.duration_ms
        return d


# ── Sanitization ─────────────────────────────────────────────────────────────

_PII_KEY_PATTERNS = re.compile(
    r"(api[_-]?key|secret|password|token|authorization|email|phone|ssn|address)",
    re.IGNORECASE,
)
_PII_VALUE_PATTERNS = [
    # Bearer / api keys: long opaque strings
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    # Email addresses
    re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9-.]+"),
]
_REDACTED = "[redacted]"
_MAX_VALUE_LEN = 512


def sanitize_attrs(attrs: dict[str, Any] | None) -> dict[str, Any]:
    """Drop/redact PII and credentials before persisting."""
    if not attrs:
        return {}
    clean: dict[str, Any] = {}
    for k, v in attrs.items():
        if not isinstance(k, str):
            k = str(k)
        if _PII_KEY_PATTERNS.search(k):
            clean[k] = _REDACTED
            continue
        clean[k] = _sanitize_value(v)
    return clean


def _sanitize_value(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        s = v
        for pat in _PII_VALUE_PATTERNS:
            s = pat.sub(_REDACTED, s)
        if len(s) > _MAX_VALUE_LEN:
            s = s[:_MAX_VALUE_LEN] + "…"
        return s
    if isinstance(v, dict):
        return sanitize_attrs(v)
    if isinstance(v, (list, tuple)):
        return [_sanitize_value(x) for x in v]
    # Fall back to str() so we never persist arbitrary objects
    return _sanitize_value(str(v))


# ── Recorder ─────────────────────────────────────────────────────────────────


class SpanRecorder:
    """In-memory recorder with optional JSONL tee + custom sinks.

    ``capacity`` bounds the in-memory ring so a long-running process
    can't blow heap during a publish-day surge. Older spans are dropped
    once the cap is reached — but the JSONL tee still has them, and the
    nightly rollup (see ``metrics.rollup_method_metrics``) materialises
    durable per-method aggregates.
    """

    def __init__(
        self,
        *,
        capacity: int = 10_000,
        jsonl_path: Path | str | None = None,
        sinks: Iterable[Callable[[Span], None]] | None = None,
    ) -> None:
        self._spans: list[Span] = []
        self._capacity = capacity
        if jsonl_path is None:
            jsonl_path = Path(
                os.environ.get(
                    "THESEUS_SPANS_FILE",
                    Path.home() / ".theseus" / "logs" / "spans.jsonl",
                )
            )
        self._jsonl_path: Path | None = Path(jsonl_path) if jsonl_path else None
        self._sinks: list[Callable[[Span], None]] = list(sinks or [])

    def add_sink(self, sink: Callable[[Span], None]) -> None:
        self._sinks.append(sink)

    def record(self, span: Span) -> None:
        # Defensive: scrub before anything else can read attrs.
        span.attrs = sanitize_attrs(span.attrs)
        self._spans.append(span)
        if len(self._spans) > self._capacity:
            # Drop oldest. Fast enough for typical capacities.
            del self._spans[: len(self._spans) - self._capacity]
        if self._jsonl_path is not None:
            try:
                self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
                with self._jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(span.to_dict(), default=str, ensure_ascii=False)
                        + "\n"
                    )
            except OSError:
                # Never let observability take down the pipeline.
                pass
        for sink in self._sinks:
            try:
                sink(span)
            except Exception:
                pass

    def spans(self) -> list[Span]:
        return list(self._spans)

    def clear(self) -> None:
        self._spans.clear()

    def by_trace(self, trace_id: str) -> list[Span]:
        return [s for s in self._spans if s.trace_id == trace_id]


_recorder: SpanRecorder | None = None


def get_recorder() -> SpanRecorder:
    global _recorder
    if _recorder is None:
        _recorder = SpanRecorder()
    return _recorder


def set_recorder(recorder: SpanRecorder | None) -> None:
    """Install a custom recorder. Pass ``None`` to reset to defaults."""
    global _recorder
    _recorder = recorder


# ── Context propagation ─────────────────────────────────────────────────────

_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "TRACE_ID", default=None
)
_SPAN_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "SPAN_ID", default=None
)


def current_trace() -> str | None:
    return _TRACE_ID.get()


def current_span() -> str | None:
    return _SPAN_ID.get()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# ── start_span / start_trace ────────────────────────────────────────────────


@contextmanager
def start_span(
    name: str,
    *,
    attrs: dict[str, Any] | None = None,
    recorder: SpanRecorder | None = None,
) -> Iterator[Span]:
    """Open a child span under the current trace.

    If no trace is active, a new one is started transparently. The
    ``trace_id``, parent ``span_id``, and a freshly minted ``span_id``
    are mirrored into ``contextvars`` so any nested ``start_span`` /
    ``start_trace`` (and any ``structlog.contextvars`` consumer) sees
    the right context.
    """
    rec = recorder or get_recorder()

    trace_id = _TRACE_ID.get()
    if trace_id is None:
        trace_id = _new_id("trace")
        trace_token = _TRACE_ID.set(trace_id)
    else:
        trace_token = None

    parent_span_id = _SPAN_ID.get()
    span_id = _new_id("span")
    span = Span(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        start=time.time(),
        attrs=sanitize_attrs(attrs),
    )
    span_token = _SPAN_ID.set(span_id)

    # Mirror into structlog so log lines get the same trace/span keys for free.
    try:
        import structlog.contextvars as _scv

        _scv.bind_contextvars(trace_id=trace_id, span_id=span_id)
    except Exception:
        _scv = None  # type: ignore[assignment]

    try:
        yield span
        if span.status == SpanStatus.OK and span.end is None:
            span.status = SpanStatus.OK
    except BaseException as exc:
        span.status = SpanStatus.ERROR
        span.error_kind = type(exc).__name__
        span.error_message = str(exc)[:500]
        raise
    finally:
        if span.end is None:
            span.end = time.time()
        rec.record(span)
        _SPAN_ID.reset(span_token)
        if trace_token is not None:
            _TRACE_ID.reset(trace_token)
        if _scv is not None:
            try:
                _scv.unbind_contextvars("span_id")
                if trace_token is not None:
                    _scv.unbind_contextvars("trace_id")
            except Exception:
                pass


@contextmanager
def start_trace(
    name: str,
    *,
    trace_id: str | None = None,
    attrs: dict[str, Any] | None = None,
    recorder: SpanRecorder | None = None,
) -> Iterator[Span]:
    """Originate a new trace, or attach to an existing one.

    Pass ``trace_id`` (e.g. extracted from an inbound HTTP header) to
    join a trace started elsewhere. Otherwise a new id is minted.
    """
    if trace_id is None:
        trace_id = _new_id("trace")
    # Reset parent span — this is a top-level boundary.
    parent_token = _SPAN_ID.set(None)
    trace_token = _TRACE_ID.set(trace_id)
    try:
        with start_span(name, attrs=attrs, recorder=recorder) as span:
            yield span
    finally:
        _TRACE_ID.reset(trace_token)
        _SPAN_ID.reset(parent_token)


# ── traced decorator ────────────────────────────────────────────────────────

_F = TypeVar("_F", bound=Callable[..., Any])

# Span store would bloat if a function called thousands of times a minute
# emitted a span per call. Hot-path functions pass ``sample_rate < 1.0``;
# sampling is deterministic (every Nth call) so coverage tests can assert
# the rate is honoured exactly rather than probabilistically.


def _stride_for(sample_rate: float) -> int:
    """Calls-between-samples for a given rate. 0 means "never sample"."""
    rate = max(0.0, min(1.0, float(sample_rate)))
    if rate >= 1.0:
        return 1
    if rate <= 0.0:
        return 0
    return max(1, round(1.0 / rate))


def _code_attrs(fn: Callable[..., Any]) -> dict[str, Any]:
    """Best-effort source location so the trace UI can link a span back
    to the line that emitted it. No PII — just module path + line."""
    try:
        code = fn.__code__  # type: ignore[attr-defined]
        filepath = code.co_filename
        marker = f"{os.sep}noosphere{os.sep}"
        idx = filepath.rfind(marker)
        if idx != -1:
            filepath = filepath[idx + 1 :]
        return {
            "code.function": getattr(fn, "__qualname__", getattr(fn, "__name__", "")),
            "code.filepath": filepath,
            "code.lineno": code.co_firstlineno,
        }
    except Exception:
        return {}


def traced(
    name: str | Callable[..., Any] | None = None,
    *,
    sample_rate: float = 1.0,
    attrs: dict[str, Any] | None = None,
    recorder: SpanRecorder | None = None,
) -> Any:
    """Wrap a function so each invocation opens a span under the current trace.

    Usable bare (``@traced``) or parameterised
    (``@traced("mqs.score_conclusion", sample_rate=0.1)``). When no
    ``name`` is given the span is named ``{module}.{qualname}``.

    ``sample_rate`` in [0, 1] throttles hot-path functions: ``0.1`` emits
    a span for every 10th call. The decision is deterministic per wrapper
    (a call counter, not a coin flip) so callers and tests get a stable,
    assertable rate. Sampled-out calls still run — only the span is skipped.

    Async functions are supported transparently; the span spans the await.

    The wrapper carries ``__traced__``/``__traced_span_name__``/
    ``__traced_sample_rate__`` markers so ``scripts/survey_trace_coverage.py``
    can tell instrumented functions from bare ones.
    """
    bare_fn: Callable[..., Any] | None = None
    if callable(name):
        bare_fn = name
        name = None

    def decorate(fn: _F) -> _F:
        span_name = name if isinstance(name, str) and name else (
            f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', fn.__name__)}"
        )
        stride = _stride_for(sample_rate)
        base_attrs = _code_attrs(fn)
        if attrs:
            base_attrs.update(attrs)
        state = {"calls": 0}

        def _sampled() -> bool:
            state["calls"] += 1
            if stride == 0:
                return False
            return (state["calls"] - 1) % stride == 0

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not _sampled():
                    return await fn(*args, **kwargs)
                with start_span(span_name, attrs=dict(base_attrs), recorder=recorder):
                    return await fn(*args, **kwargs)

            wrapper: Callable[..., Any] = async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not _sampled():
                    return fn(*args, **kwargs)
                with start_span(span_name, attrs=dict(base_attrs), recorder=recorder):
                    return fn(*args, **kwargs)

            wrapper = sync_wrapper

        wrapper.__traced__ = True  # type: ignore[attr-defined]
        wrapper.__traced_span_name__ = span_name  # type: ignore[attr-defined]
        wrapper.__traced_sample_rate__ = max(  # type: ignore[attr-defined]
            0.0, min(1.0, float(sample_rate))
        )
        return wrapper  # type: ignore[return-value]

    if bare_fn is not None:
        return decorate(bare_fn)
    return decorate
