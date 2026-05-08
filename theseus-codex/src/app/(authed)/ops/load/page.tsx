import Link from "next/link";

import {
  listLoadRuns,
  trendByProfile,
  type LoadProfileName,
  type LoadRun,
  type LoadTrendPoint,
} from "@/lib/loadTestData";

/**
 * Operator dashboard: load-test trend + recent runs.
 *
 * Renders trend lines for each profile (light / viral / spike) and a
 * table of the last N runs. Each row links to the raw JSON artifact so
 * an operator chasing a regression can drill in without leaving the
 * page.
 *
 * The data comes from `tests/load/results/*.json`, which the GitHub
 * workflows populate (and locally, the harness CLI). If the directory
 * doesn't exist, the page renders an empty state explaining how to
 * trigger a run.
 */

export const dynamic = "force-dynamic";

const PROFILES: LoadProfileName[] = ["light", "viral", "spike"];

function formatPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function formatMs(value: number): string {
  return `${Math.round(value)}ms`;
}

function formatTimestamp(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function Sparkline({
  points,
  field,
}: {
  points: LoadTrendPoint[];
  field: "p50Ms" | "p95Ms" | "errorRate";
}) {
  if (points.length === 0) {
    return <span className="text-xs text-gray-500">no runs</span>;
  }
  const values = points.map((p) => p[field]);
  const max = Math.max(...values, field === "errorRate" ? 0.01 : 1);
  const min = Math.min(...values, 0);
  const W = 120;
  const H = 30;
  const pad = 2;
  const stepX = points.length > 1 ? (W - pad * 2) / (points.length - 1) : 0;
  const yFor = (v: number) => {
    const span = max - min || 1;
    const norm = (v - min) / span;
    return H - pad - norm * (H - pad * 2);
  };
  const path = values
    .map((v, i) => `${i === 0 ? "M" : "L"} ${pad + i * stepX} ${yFor(v)}`)
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      role="img"
      aria-label={`${field} trend`}
    >
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.25}
      />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={pad + i * stepX}
          cy={yFor(values[i])}
          r={p.passed ? 1.5 : 2.5}
          fill={p.passed ? "currentColor" : "#dc2626"}
        />
      ))}
    </svg>
  );
}

function ProfileSummary({
  profile,
  trend,
}: {
  profile: LoadProfileName;
  trend: LoadTrendPoint[];
}) {
  const last = trend[trend.length - 1];
  return (
    <div className="rounded border border-gray-300 p-3">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide">
          {profile}
        </h3>
        <span className="text-xs text-gray-500">
          {trend.length} run{trend.length === 1 ? "" : "s"}
        </span>
      </div>
      {last ? (
        <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
          <div>
            <dt className="text-gray-500">p50</dt>
            <dd>{formatMs(last.p50Ms)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">p95</dt>
            <dd>{formatMs(last.p95Ms)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">err</dt>
            <dd>{formatPct(last.errorRate)}</dd>
          </div>
        </dl>
      ) : (
        <p className="mt-2 text-xs text-gray-500">no data yet</p>
      )}
      <div className="mt-3 flex flex-col gap-1 text-gray-700">
        <div className="flex items-center gap-2 text-xs">
          <span className="w-10 text-gray-500">p50</span>
          <Sparkline points={trend} field="p50Ms" />
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="w-10 text-gray-500">p95</span>
          <Sparkline points={trend} field="p95Ms" />
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="w-10 text-gray-500">err</span>
          <Sparkline points={trend} field="errorRate" />
        </div>
      </div>
    </div>
  );
}

function RunRow({ run }: { run: LoadRun }) {
  const verdictLabel = run.verdict.passed
    ? "PASS"
    : run.overrideReason
      ? "OVERRIDE"
      : "FAIL";
  const verdictClass = run.verdict.passed
    ? "text-green-700"
    : run.overrideReason
      ? "text-amber-700"
      : "text-red-700";
  return (
    <tr className="border-b border-gray-200">
      <td className="px-2 py-1 font-mono text-xs">
        {formatTimestamp(run.startedAt)}
      </td>
      <td className="px-2 py-1 text-xs uppercase">{run.profile}</td>
      <td className="px-2 py-1 text-xs">{run.samples}</td>
      <td className="px-2 py-1 text-xs">{formatMs(run.stats.p50Ms)}</td>
      <td className="px-2 py-1 text-xs">{formatMs(run.stats.p95Ms)}</td>
      <td className="px-2 py-1 text-xs">{formatPct(run.stats.errorRate)}</td>
      <td className="px-2 py-1 text-xs">
        {run.stats.poolExhaustionEvents}
      </td>
      <td className={`px-2 py-1 text-xs font-semibold ${verdictClass}`}>
        {verdictLabel}
      </td>
      <td className="px-2 py-1 text-xs text-gray-600">
        {run.overrideReason ? (
          <span title={run.overrideReason}>
            override: {run.overrideReason.slice(0, 40)}
            {run.overrideReason.length > 40 ? "…" : ""}
          </span>
        ) : run.verdict.reasons[0] ? (
          <span title={run.verdict.reasons.join("; ")}>
            {run.verdict.reasons[0]}
          </span>
        ) : (
          ""
        )}
      </td>
    </tr>
  );
}

export default async function OpsLoadPage() {
  const runs = await listLoadRuns(50);
  const trend = trendByProfile(runs);

  return (
    <main className="mx-auto max-w-5xl px-4 py-6">
      <header className="mb-4">
        <p className="text-xs text-gray-500">
          <Link href="/ops" className="underline">
            ← Ops
          </Link>
        </p>
        <h1 className="text-2xl font-semibold">Public-site load test</h1>
        <p className="mt-1 text-sm text-gray-600">
          Synthetic viral-traffic simulator. The harness opens K
          concurrent reader sessions against a deploy and verifies the
          public site stays under the budget (p50 &lt; 1.0s,
          p95 &lt; 3.0s, errors &lt; 1.0%, no DB pool exhaustion).
        </p>
        <p className="mt-2 text-xs text-gray-500">
          Light runs on every preview deploy. Viral runs nightly
          against staging. Spike is manual-trigger only — see{" "}
          <code>.github/workflows/load_test_nightly.yml</code>.
        </p>
      </header>

      <section className="mb-6 grid gap-3 sm:grid-cols-3">
        {PROFILES.map((profile) => (
          <ProfileSummary
            key={profile}
            profile={profile}
            trend={trend[profile]}
          />
        ))}
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Recent runs</h2>
        {runs.length === 0 ? (
          <p className="text-sm text-gray-600">
            No runs yet. Run{" "}
            <code>python tests/load/article_viral.py --profile light</code>{" "}
            locally, or wait for the next preview deploy to trigger one.
          </p>
        ) : (
          <table className="w-full border-collapse text-left">
            <thead className="border-b border-gray-300">
              <tr>
                <th className="px-2 py-1 text-xs">started</th>
                <th className="px-2 py-1 text-xs">profile</th>
                <th className="px-2 py-1 text-xs">samples</th>
                <th className="px-2 py-1 text-xs">p50</th>
                <th className="px-2 py-1 text-xs">p95</th>
                <th className="px-2 py-1 text-xs">err</th>
                <th className="px-2 py-1 text-xs" title="DB pool exhaustion events">
                  pool
                </th>
                <th className="px-2 py-1 text-xs">verdict</th>
                <th className="px-2 py-1 text-xs">notes</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <RunRow key={run.runId + run.filename} run={run} />
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
