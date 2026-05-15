"""Span instrumentation for outbound third-party API calls.

Every request to OpenAI, Anthropic, Voyage, Polymarket, Kalshi,
Retraction Watch, etc. should be wrapped here so that a trace shows not
just "the pipeline ran" but "the pipeline spent 2.1s in three Voyage
embedding calls, one of which retried twice and 429'd". The span name is
``external.{provider}`` and the attributes carry the route, model,
status code, and retry count.

Two surfaces:

* ``external_call(...)`` — a context manager yielding a handle the caller
  stamps as the request progresses (``set_status_code``, ``record_retry``,
  ``set_attr``). Errors raised inside the block are recorded by the
  underlying span machinery (status → error, ``error_kind`` / message set)
  and re-raised.
* ``traced_request(...)`` — a thin wrapper for the common
  "call this thunk, retrying on exception" loop, so call sites that don't
  need fine-grained control get retry-count attribution for free.

Privacy: only structural metadata is recorded — provider, route, model,
status, retry/latency counters. Request/response bodies, prompts, API
keys, and headers are never passed through here. ``sanitize_attrs`` in
``spans`` is the backstop, but the contract is "don't hand it secrets".
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar

from noosphere.observability.spans import Span, SpanRecorder, start_span

# ── Provider identifiers ────────────────────────────────────────────────────
#
# Stable strings — the dashboard groups external spans by these, so don't
# rename without a rollup migration.

PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_VOYAGE = "voyage"
PROVIDER_POLYMARKET = "polymarket"
PROVIDER_KALSHI = "kalshi"
PROVIDER_RETRACTION_WATCH = "retraction_watch"

KNOWN_PROVIDERS: frozenset[str] = frozenset(
    {
        PROVIDER_OPENAI,
        PROVIDER_ANTHROPIC,
        PROVIDER_VOYAGE,
        PROVIDER_POLYMARKET,
        PROVIDER_KALSHI,
        PROVIDER_RETRACTION_WATCH,
    }
)


# ── Call handle ─────────────────────────────────────────────────────────────


class ExternalCallSpan:
    """Mutable handle over the span backing one external request.

    The caller stamps the response shape as it learns it. All setters are
    no-throw — observability must never be the thing that breaks a request
    path.
    """

    __slots__ = ("_span", "provider", "route", "retry_count")

    def __init__(self, span: Span, *, provider: str, route: str) -> None:
        self._span = span
        self.provider = provider
        self.route = route
        self.retry_count = 0

    @property
    def span(self) -> Span:
        return self._span

    def set_status_code(self, status_code: int | None) -> None:
        """HTTP status of the (final) response."""
        if status_code is None:
            return
        try:
            self._span.attrs["status_code"] = int(status_code)
        except Exception:
            pass

    def record_retry(self) -> None:
        """Bump the retry counter — call once per re-attempt."""
        self.retry_count += 1
        self._span.attrs["retry_count"] = self.retry_count

    def set_attr(self, key: str, value: Any) -> None:
        """Attach an extra structural attribute (model variant, token
        count, region…). Never pass request/response bodies."""
        try:
            self._span.attrs[str(key)] = value
        except Exception:
            pass

    def set_model(self, model: str | None) -> None:
        if model:
            self._span.attrs["model"] = str(model)


# ── Context manager ─────────────────────────────────────────────────────────


@contextmanager
def external_call(
    provider: str,
    *,
    route: str,
    model: str | None = None,
    attrs: dict[str, Any] | None = None,
    recorder: SpanRecorder | None = None,
) -> Iterator[ExternalCallSpan]:
    """Open a span around one outbound API request.

    ``provider`` should be one of the ``PROVIDER_*`` constants (unknown
    values are still accepted — they just won't group with the known set
    on the dashboard). ``route`` is the logical endpoint, e.g.
    ``"/v1/messages"`` or ``"markets.list"``.

    Exceptions raised inside the block propagate; the span records them
    as an error (``error_kind`` / ``error_message`` set by ``start_span``)
    and stamps the final ``retry_count`` so a failed call still shows how
    hard it tried.
    """
    span_attrs: dict[str, Any] = {
        "provider": provider,
        "route": route,
        "retry_count": 0,
    }
    if model:
        span_attrs["model"] = model
    if attrs:
        span_attrs.update(attrs)

    started = time.time()
    with start_span(
        f"external.{provider}", attrs=span_attrs, recorder=recorder
    ) as span:
        handle = ExternalCallSpan(span, provider=provider, route=route)
        try:
            yield handle
        finally:
            # Latency is also derivable from start/end, but a flat attr
            # keeps the dashboard's external-call table a pure projection.
            span.attrs["latency_ms"] = round((time.time() - started) * 1000.0, 2)
            span.attrs["retry_count"] = handle.retry_count


# ── Retry-loop convenience wrapper ──────────────────────────────────────────

_T = TypeVar("_T")


def traced_request(
    provider: str,
    *,
    route: str,
    request: Callable[[], _T],
    model: str | None = None,
    max_retries: int = 0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    status_of: Callable[[_T], int | None] | None = None,
    attrs: dict[str, Any] | None = None,
    recorder: SpanRecorder | None = None,
) -> _T:
    """Run ``request()`` inside an ``external.{provider}`` span, retrying
    on the given exception types up to ``max_retries`` times.

    Each retry bumps the span's ``retry_count``. On success ``status_of``
    (when supplied) is used to stamp ``status_code`` from the result. The
    final exception is recorded and re-raised when retries are exhausted.
    """
    with external_call(
        provider,
        route=route,
        model=model,
        attrs=attrs,
        recorder=recorder,
    ) as handle:
        attempt = 0
        while True:
            try:
                result = request()
            except retry_on as exc:  # noqa: B902 - caller-supplied tuple
                if attempt >= max_retries:
                    handle.set_attr("failed_after_attempts", attempt + 1)
                    raise
                attempt += 1
                handle.record_retry()
                last_exc = exc  # noqa: F841 - kept for debuggers
                continue
            if status_of is not None:
                try:
                    handle.set_status_code(status_of(result))
                except Exception:
                    pass
            return result


__all__ = [
    "ExternalCallSpan",
    "KNOWN_PROVIDERS",
    "PROVIDER_ANTHROPIC",
    "PROVIDER_KALSHI",
    "PROVIDER_OPENAI",
    "PROVIDER_POLYMARKET",
    "PROVIDER_RETRACTION_WATCH",
    "PROVIDER_VOYAGE",
    "external_call",
    "traced_request",
]
