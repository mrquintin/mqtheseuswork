import { db } from "@/lib/db";

/**
 * Read API for the operator dashboard.
 *
 * The Python pipeline writes spans to Postgres (table `Span`) under a
 * shared `traceId`; the nightly rollup populates `MethodMetricRollup`
 * so trendlines stay queryable past span retention. This file is the
 * only place the dashboard talks to those tables — keep aggregations
 * here so the page can stay a thin renderer.
 */

export type SpanRow = {
  id: string;
  traceId: string;
  parentSpanId: string | null;
  name: string;
  status: string;
  startedAt: Date;
  endedAt: Date | null;
  durationMs: number | null;
  errorKind: string | null;
  errorMessage: string | null;
  attrs: Record<string, unknown>;
  costUsd: number;
};

export type TraceSummary = {
  traceId: string;
  startedAt: Date;
  endedAt: Date | null;
  durationMs: number | null;
  spanCount: number;
  errorCount: number;
  rootName: string;
  status: "ok" | "error" | "in_flight";
};

export type MethodMetricRow = {
  method: string;
  count: number;
  errorCount: number;
  errorRate: number;
  p50Ms: number;
  p95Ms: number;
  costUsd: number;
  windowStart: Date;
  windowEnd: Date;
};

export type AlertEventRow = {
  id: string;
  ruleName: string;
  method: string;
  metric: string;
  value: number;
  threshold: number;
  firedAt: Date;
  acknowledgedAt: Date | null;
};

export type CostBudget = {
  spentUsd: number;
  budgetUsd: number;
  windowStart: Date;
  windowEnd: Date;
};

const DEFAULT_TRACE_LIMIT = 25;

function toRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function spanFromDb(row: {
  id: string;
  traceId: string;
  parentSpanId: string | null;
  name: string;
  status: string;
  startedAt: Date;
  endedAt: Date | null;
  durationMs: number | null;
  errorKind: string | null;
  errorMessage: string | null;
  attrs: unknown;
  costUsd: number;
}): SpanRow {
  return {
    id: row.id,
    traceId: row.traceId,
    parentSpanId: row.parentSpanId,
    name: row.name,
    status: row.status,
    startedAt: row.startedAt,
    endedAt: row.endedAt,
    durationMs: row.durationMs,
    errorKind: row.errorKind,
    errorMessage: row.errorMessage,
    attrs: toRecord(row.attrs),
    costUsd: row.costUsd,
  };
}

/**
 * Recent traces, newest first. A trace is in_flight if any span is open
 * (no `endedAt`) — the dashboard surfaces these prominently during a
 * publish-day surge.
 */
export async function listRecentTraces(
  limit = DEFAULT_TRACE_LIMIT,
): Promise<TraceSummary[]> {
  const rows = await db.span.findMany({
    orderBy: { startedAt: "desc" },
    take: limit * 12, // overshoot, then group by trace
  });

  const byTrace = new Map<string, SpanRow[]>();
  for (const row of rows) {
    const span = spanFromDb(row);
    const list = byTrace.get(span.traceId) ?? [];
    list.push(span);
    byTrace.set(span.traceId, list);
  }

  const summaries: TraceSummary[] = [];
  for (const [traceId, spans] of byTrace) {
    spans.sort((a, b) => a.startedAt.getTime() - b.startedAt.getTime());
    const root = spans.find((s) => s.parentSpanId === null) ?? spans[0];
    const allClosed = spans.every((s) => s.endedAt !== null);
    const lastEnd = allClosed
      ? new Date(
          Math.max(...spans.map((s) => (s.endedAt as Date).getTime())),
        )
      : null;
    const errorCount = spans.filter((s) => s.status === "error").length;
    summaries.push({
      traceId,
      startedAt: root.startedAt,
      endedAt: lastEnd,
      durationMs:
        lastEnd === null ? null : lastEnd.getTime() - root.startedAt.getTime(),
      spanCount: spans.length,
      errorCount,
      rootName: root.name,
      status: !allClosed ? "in_flight" : errorCount > 0 ? "error" : "ok",
    });
  }
  summaries.sort((a, b) => b.startedAt.getTime() - a.startedAt.getTime());
  return summaries.slice(0, limit);
}

export async function listInFlightTraces(): Promise<TraceSummary[]> {
  const all = await listRecentTraces(100);
  return all.filter((t) => t.status === "in_flight");
}

export async function getTrace(traceId: string): Promise<SpanRow[]> {
  const rows = await db.span.findMany({
    where: { traceId },
    orderBy: { startedAt: "asc" },
  });
  return rows.map(spanFromDb);
}

export async function getMethodMetrics(
  options: { sinceDays?: number } = {},
): Promise<MethodMetricRow[]> {
  const sinceDays = options.sinceDays ?? 7;
  const since = new Date(Date.now() - sinceDays * 24 * 60 * 60 * 1000);
  const rows = await db.methodMetricRollup.findMany({
    where: { windowStart: { gte: since } },
    orderBy: { windowStart: "desc" },
  });
  return rows.map((r) => ({
    method: r.method,
    count: r.count,
    errorCount: r.errorCount,
    errorRate: r.errorRate,
    p50Ms: r.p50Ms,
    p95Ms: r.p95Ms,
    costUsd: r.costUsd,
    windowStart: r.windowStart,
    windowEnd: r.windowEnd,
  }));
}

export async function listRecentAlerts(limit = 25): Promise<AlertEventRow[]> {
  const rows = await db.alertEvent.findMany({
    orderBy: { firedAt: "desc" },
    take: limit,
  });
  return rows.map((r) => ({
    id: r.id,
    ruleName: r.ruleName,
    method: r.method,
    metric: r.metric,
    value: r.value,
    threshold: r.threshold,
    firedAt: r.firedAt,
    acknowledgedAt: r.acknowledgedAt,
  }));
}

/**
 * Cost spent in the trailing 24h vs daily budget. Read from env until
 * a per-tenant budget surface lands.
 */
export async function getCostBurndown(): Promise<CostBudget> {
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000);
  const aggregate = await db.span.aggregate({
    where: { startedAt: { gte: since } },
    _sum: { costUsd: true },
  });
  const spent = aggregate._sum.costUsd ?? 0;
  const budget = Number(process.env.NOOSPHERE_DAILY_BUDGET_USD ?? "50") || 50;
  return {
    spentUsd: spent,
    budgetUsd: budget,
    windowStart: since,
    windowEnd: new Date(),
  };
}

/**
 * Number of error spans bucketed by hour over the trailing window.
 * Powers the "error spikes" sparkline.
 */
export async function getErrorSparkline(
  hours = 24,
): Promise<Array<{ hour: Date; errorCount: number; total: number }>> {
  const since = new Date(Date.now() - hours * 60 * 60 * 1000);
  const rows = await db.span.findMany({
    where: { startedAt: { gte: since } },
    select: { startedAt: true, status: true },
  });
  const buckets = new Map<number, { errorCount: number; total: number }>();
  for (const r of rows) {
    const hourStart = new Date(r.startedAt);
    hourStart.setMinutes(0, 0, 0);
    const key = hourStart.getTime();
    const slot = buckets.get(key) ?? { errorCount: 0, total: 0 };
    slot.total += 1;
    if (r.status === "error") slot.errorCount += 1;
    buckets.set(key, slot);
  }
  const out: Array<{ hour: Date; errorCount: number; total: number }> = [];
  for (let i = hours - 1; i >= 0; i--) {
    const hour = new Date(Date.now() - i * 60 * 60 * 1000);
    hour.setMinutes(0, 0, 0);
    const slot = buckets.get(hour.getTime()) ?? { errorCount: 0, total: 0 };
    out.push({ hour, errorCount: slot.errorCount, total: slot.total });
  }
  return out;
}
