"""
Method-level metrics + alerting on top of spans.

The same nightly job that materialises track-record (prompt 02) calls
``rollup_method_metrics`` to write per-method windows so the dashboard
doesn't have to scan raw spans. Spans older than ``retention_days``
(default 30) can then be purged: the rollup is the durable record.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from noosphere.observability.spans import Span, SpanStatus


# ── Per-method rollup ────────────────────────────────────────────────────────


@dataclass
class MethodMetrics:
    method: str
    count: int
    error_count: int
    p50_ms: float
    p95_ms: float
    error_rate: float
    cost_usd: float
    window_start: datetime | None = None
    window_end: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "count": self.count,
            "error_count": self.error_count,
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "error_rate": round(self.error_rate, 4),
            "cost_usd": round(self.cost_usd, 4),
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
        }


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    s = sorted(values)
    # Nearest-rank percentile — fine for ops dashboards, no scipy needed.
    k = max(0, min(len(s) - 1, int(round(pct / 100.0 * (len(s) - 1)))))
    return s[k]


def rollup_method_metrics(
    spans: Iterable[Span],
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> list[MethodMetrics]:
    """Aggregate completed spans by ``name`` into per-method metrics.

    Cost is read from ``span.attrs["cost_usd"]`` when present (the LLM
    wrappers tag it). Open spans (``end is None``) are skipped — they
    haven't completed yet, so latency is undefined.
    """
    by_method: dict[str, list[Span]] = {}
    for s in spans:
        if s.end is None:
            continue
        by_method.setdefault(s.name, []).append(s)

    out: list[MethodMetrics] = []
    for method, group in by_method.items():
        durations = [s.duration_ms or 0.0 for s in group]
        errors = [s for s in group if s.status == SpanStatus.ERROR]
        cost = 0.0
        for s in group:
            v = s.attrs.get("cost_usd") if s.attrs else None
            if isinstance(v, (int, float)):
                cost += float(v)
        out.append(
            MethodMetrics(
                method=method,
                count=len(group),
                error_count=len(errors),
                p50_ms=_percentile(durations, 50),
                p95_ms=_percentile(durations, 95),
                error_rate=(len(errors) / len(group)) if group else 0.0,
                cost_usd=cost,
                window_start=window_start,
                window_end=window_end,
            )
        )
    out.sort(key=lambda m: m.count, reverse=True)
    return out


# ── Alerting ─────────────────────────────────────────────────────────────────


@dataclass
class AlertRule:
    """Threshold-based alert rule.

    ``metric`` is one of ``error_rate``, ``p95_ms``, ``cost_usd``,
    ``count``. ``method`` of ``"*"`` matches any method (rule fires
    once for whichever method first crosses the threshold).
    """

    name: str
    metric: str
    threshold: float
    method: str = "*"
    window_minutes: int = 15
    min_samples: int = 5

    def evaluate(self, metrics: list[MethodMetrics]) -> "AlertEvent | None":
        for m in metrics:
            if self.method != "*" and m.method != self.method:
                continue
            if m.count < self.min_samples:
                continue
            value = getattr(m, self.metric, None)
            if value is None:
                continue
            if value > self.threshold:
                return AlertEvent(
                    rule_name=self.name,
                    method=m.method,
                    metric=self.metric,
                    value=float(value),
                    threshold=self.threshold,
                    fired_at=datetime.now(tz=timezone.utc),
                )
        return None


@dataclass
class AlertEvent:
    rule_name: str
    method: str
    metric: str
    value: float
    threshold: float
    fired_at: datetime
    delivered_to: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rule_name": self.rule_name,
            "method": self.method,
            "metric": self.metric,
            "value": round(self.value, 4),
            "threshold": self.threshold,
            "fired_at": self.fired_at.isoformat(),
            "delivered_to": list(self.delivered_to),
        }


def evaluate_alerts(
    metrics: list[MethodMetrics],
    rules: Iterable[AlertRule],
) -> list[AlertEvent]:
    out: list[AlertEvent] = []
    for rule in rules:
        ev = rule.evaluate(metrics)
        if ev is not None:
            out.append(ev)
    return out


# ── Default rules ────────────────────────────────────────────────────────────

DEFAULT_RULES: list[AlertRule] = [
    AlertRule(
        name="method_error_rate_high",
        metric="error_rate",
        threshold=0.05,
        window_minutes=15,
        min_samples=5,
    ),
    AlertRule(
        name="method_p95_slow",
        metric="p95_ms",
        threshold=30_000.0,  # 30s
        window_minutes=15,
        min_samples=5,
    ),
]
