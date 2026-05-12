"""Database persistence for Noosphere spans and Ops rollups."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from noosphere.observability.metrics import DEFAULT_RULES, evaluate_alerts, rollup_method_metrics
from noosphere.observability.spans import Span, get_recorder


_UNSUPPORTED_QUERY_PARAMS = {"pgbouncer", "connection_limit", "pool_timeout"}
_INSTALLED_SPAN_SINKS: set[str] = set()


@dataclass(frozen=True)
class OpsRollupReport:
    span_count: int
    rollup_count: int
    alert_count: int
    window_start: datetime
    window_end: datetime
    errors: list[str]


def _database_url(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for key in (
        "THESEUS_CODEX_DATABASE_URL",
        "CODEX_DATABASE_URL",
        "DIRECT_URL",
        "DATABASE_URL",
    ):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    raise RuntimeError("No database URL found for observability persistence")


def _sqlalchemy_url(url: str) -> str:
    if "?" not in url:
        return url
    parts = urlsplit(url)
    if parts.scheme not in {"postgres", "postgresql"}:
        return url
    filtered = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _UNSUPPORTED_QUERY_PARAMS
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(filtered), parts.fragment)
    )


def _engine(database_url: str | None = None) -> Engine:
    return create_engine(_sqlalchemy_url(_database_url(database_url)))


def _utc_from_epoch(value: float | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise TypeError(f"cannot coerce {value!r} to datetime")


def _coerce_attrs(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def persist_span(engine: Engine, span: Span) -> None:
    attrs = dict(span.attrs or {})
    cost = attrs.get("cost_usd")
    if not isinstance(cost, (int, float)):
        cost = 0.0
    payload = {
        "id": span.span_id,
        "traceId": span.trace_id,
        "parentSpanId": span.parent_span_id,
        "name": span.name,
        "status": span.status,
        "startedAt": _utc_from_epoch(span.start),
        "endedAt": _utc_from_epoch(span.end),
        "durationMs": span.duration_ms,
        "errorKind": span.error_kind,
        "errorMessage": span.error_message,
        "attrs": json.dumps(attrs, default=str),
        "costUsd": float(cost),
        "organizationId": attrs.get("organization_id") if isinstance(attrs.get("organization_id"), str) else None,
    }
    if engine.dialect.name == "postgresql":
        stmt = text(
            '''INSERT INTO "Span"
               ("id", "traceId", "parentSpanId", "name", "status", "startedAt", "endedAt",
                "durationMs", "errorKind", "errorMessage", "attrs", "costUsd", "organizationId")
               VALUES (:id, :traceId, :parentSpanId, :name, :status, :startedAt, :endedAt,
                       :durationMs, :errorKind, :errorMessage, CAST(:attrs AS jsonb), :costUsd, :organizationId)
               ON CONFLICT ("id") DO NOTHING'''
        )
    else:
        stmt = text(
            '''INSERT OR IGNORE INTO "Span"
               ("id", "traceId", "parentSpanId", "name", "status", "startedAt", "endedAt",
                "durationMs", "errorKind", "errorMessage", "attrs", "costUsd", "organizationId")
               VALUES (:id, :traceId, :parentSpanId, :name, :status, :startedAt, :endedAt,
                       :durationMs, :errorKind, :errorMessage, :attrs, :costUsd, :organizationId)'''
        )
    with engine.begin() as conn:
        conn.execute(stmt, payload)


def install_database_span_recorder(database_url: str | None = None) -> None:
    url = _sqlalchemy_url(_database_url(database_url))
    if url in _INSTALLED_SPAN_SINKS:
        return
    engine = create_engine(url)

    def _sink(span: Span) -> None:
        try:
            persist_span(engine, span)
        except Exception:
            # Observability must never break the pipeline it observes.
            return

    get_recorder().add_sink(_sink)
    _INSTALLED_SPAN_SINKS.add(url)


def install_database_span_recorder_from_env() -> None:
    raw = os.environ.get("NOOSPHERE_DB_SPANS", "").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return
    try:
        install_database_span_recorder()
    except Exception:
        return


def _fetch_spans(engine: Engine, *, window_start: datetime, window_end: datetime) -> list[Span]:
    stmt = text(
        '''SELECT "id", "traceId", "parentSpanId", "name", "status", "startedAt", "endedAt",
                  "durationMs", "errorKind", "errorMessage", "attrs", "costUsd"
           FROM "Span"
           WHERE "startedAt" >= :window_start AND "startedAt" < :window_end'''
    )
    spans: list[Span] = []
    with engine.connect() as conn:
        for row in conn.execute(stmt, {"window_start": window_start, "window_end": window_end}).mappings():
            started = _coerce_datetime(row["startedAt"])
            ended = _coerce_datetime(row["endedAt"]) if row["endedAt"] is not None else None
            attrs = _coerce_attrs(row["attrs"])
            if row["costUsd"]:
                attrs.setdefault("cost_usd", float(row["costUsd"]))
            spans.append(
                Span(
                    trace_id=str(row["traceId"]),
                    span_id=str(row["id"]),
                    parent_span_id=row["parentSpanId"],
                    name=str(row["name"]),
                    start=started.timestamp(),
                    end=ended.timestamp() if ended else None,
                    status=str(row["status"]),
                    attrs=attrs,
                    error_kind=row["errorKind"],
                    error_message=row["errorMessage"],
                )
            )
    return spans


def _upsert_rollups(engine: Engine, metrics: list[Any], *, window_start: datetime, window_end: datetime) -> int:
    count = 0
    with engine.begin() as conn:
        for metric in metrics:
            payload = {
                "id": _stable_id("mmr", metric.method, window_start.isoformat(), window_end.isoformat()),
                "method": metric.method,
                "windowStart": window_start,
                "windowEnd": window_end,
                "count": metric.count,
                "errorCount": metric.error_count,
                "p50Ms": metric.p50_ms,
                "p95Ms": metric.p95_ms,
                "errorRate": metric.error_rate,
                "costUsd": metric.cost_usd,
            }
            if engine.dialect.name == "postgresql":
                stmt = text(
                    '''INSERT INTO "MethodMetricRollup"
                       ("id", "method", "windowStart", "windowEnd", "count", "errorCount",
                        "p50Ms", "p95Ms", "errorRate", "costUsd")
                       VALUES (:id, :method, :windowStart, :windowEnd, :count, :errorCount,
                               :p50Ms, :p95Ms, :errorRate, :costUsd)
                       ON CONFLICT ("method", "windowStart", "windowEnd") DO UPDATE SET
                         "count" = EXCLUDED."count",
                         "errorCount" = EXCLUDED."errorCount",
                         "p50Ms" = EXCLUDED."p50Ms",
                         "p95Ms" = EXCLUDED."p95Ms",
                         "errorRate" = EXCLUDED."errorRate",
                         "costUsd" = EXCLUDED."costUsd"'''
                )
            else:
                stmt = text(
                    '''INSERT INTO "MethodMetricRollup"
                       ("id", "method", "windowStart", "windowEnd", "count", "errorCount",
                        "p50Ms", "p95Ms", "errorRate", "costUsd")
                       VALUES (:id, :method, :windowStart, :windowEnd, :count, :errorCount,
                               :p50Ms, :p95Ms, :errorRate, :costUsd)
                       ON CONFLICT ("method", "windowStart", "windowEnd") DO UPDATE SET
                         "count" = excluded."count",
                         "errorCount" = excluded."errorCount",
                         "p50Ms" = excluded."p50Ms",
                         "p95Ms" = excluded."p95Ms",
                         "errorRate" = excluded."errorRate",
                         "costUsd" = excluded."costUsd"'''
                )
            conn.execute(stmt, payload)
            count += 1
    return count


def _insert_alerts(engine: Engine, alerts: list[Any], *, window_start: datetime, window_end: datetime) -> int:
    count = 0
    with engine.begin() as conn:
        for alert in alerts:
            payload = {
                "id": _stable_id("alert", alert.rule_name, alert.method, alert.metric, window_start.isoformat(), window_end.isoformat()),
                "ruleName": alert.rule_name,
                "method": alert.method,
                "metric": alert.metric,
                "value": alert.value,
                "threshold": alert.threshold,
                "firedAt": alert.fired_at,
                "deliveredTo": json.dumps(alert.delivered_to),
            }
            if engine.dialect.name == "postgresql":
                stmt = text(
                    '''INSERT INTO "AlertEvent"
                       ("id", "ruleName", "method", "metric", "value", "threshold", "firedAt", "deliveredTo")
                       VALUES (:id, :ruleName, :method, :metric, :value, :threshold, :firedAt, CAST(:deliveredTo AS jsonb))
                       ON CONFLICT ("id") DO NOTHING'''
                )
            else:
                stmt = text(
                    '''INSERT OR IGNORE INTO "AlertEvent"
                       ("id", "ruleName", "method", "metric", "value", "threshold", "firedAt", "deliveredTo")
                       VALUES (:id, :ruleName, :method, :metric, :value, :threshold, :firedAt, :deliveredTo)'''
                )
            result = conn.execute(stmt, payload)
            count += max(0, int(result.rowcount or 0))
    return count


def run_ops_rollup(
    *,
    database_url: str | None = None,
    window_hours: int = 24,
    now: datetime | None = None,
) -> OpsRollupReport:
    window_end = now or datetime.now(timezone.utc)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    window_start = window_end - timedelta(hours=max(1, int(window_hours)))
    engine = _engine(database_url)
    errors: list[str] = []
    try:
        spans = _fetch_spans(engine, window_start=window_start, window_end=window_end)
    except Exception as exc:
        return OpsRollupReport(
            span_count=0,
            rollup_count=0,
            alert_count=0,
            window_start=window_start,
            window_end=window_end,
            errors=[f"fetch_spans:{type(exc).__name__}: {exc}"],
        )
    metrics = rollup_method_metrics(spans, window_start=window_start, window_end=window_end)
    try:
        rollup_count = _upsert_rollups(
            engine,
            metrics,
            window_start=window_start,
            window_end=window_end,
        )
    except Exception as exc:
        rollup_count = 0
        errors.append(f"upsert_rollups:{type(exc).__name__}: {exc}")

    alerts = evaluate_alerts(metrics, DEFAULT_RULES)
    try:
        alert_count = _insert_alerts(
            engine,
            alerts,
            window_start=window_start,
            window_end=window_end,
        )
    except Exception as exc:
        alert_count = 0
        errors.append(f"insert_alerts:{type(exc).__name__}: {exc}")

    return OpsRollupReport(
        span_count=len(spans),
        rollup_count=rollup_count,
        alert_count=alert_count,
        window_start=window_start,
        window_end=window_end,
        errors=errors,
    )
