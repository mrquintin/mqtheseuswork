import Link from "next/link";

import { getCIDashboard, type WorkflowHealth } from "@/lib/ciHealth";

/**
 * Operator dashboard: CI health.
 *
 * One row per workflow that ships in `.github/workflows/`. Columns:
 * green/red status, p50 wall-clock time over the last ~30 runs,
 * 30-run flake rate. The quarantine list is parsed from
 * `.github/workflows/_quarantine.md`; quarantined rows render with
 * an explicit banner above the table.
 *
 * Reads from the GitHub API via the founder's existing
 * `GITHUB_DISPATCH_TOKEN`. If the token isn't set, the page renders
 * an empty state explaining how to wire it up — no 500.
 */

export const dynamic = "force-dynamic";

function formatMs(value: number): string {
  if (!value) return "—";
  if (value < 60_000) return `${(value / 1000).toFixed(1)}s`;
  const m = Math.floor(value / 60_000);
  const s = Math.round((value % 60_000) / 1000);
  return `${m}m${s.toString().padStart(2, "0")}s`;
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatTimestamp(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function StatusPill({ status }: { status: WorkflowHealth["status"] }) {
  const map: Record<WorkflowHealth["status"], { label: string; cls: string }> = {
    green: { label: "green", cls: "bg-green-100 text-green-800" },
    red: { label: "red", cls: "bg-red-100 text-red-800" },
    in_progress: { label: "running", cls: "bg-blue-100 text-blue-800" },
    unknown: { label: "—", cls: "bg-gray-100 text-gray-700" },
  };
  const { label, cls } = map[status];
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${cls}`}
    >
      {label}
    </span>
  );
}

function FlakeCell({ rate }: { rate: number }) {
  const cls =
    rate >= 0.05
      ? "text-red-700 font-semibold"
      : rate >= 0.02
        ? "text-amber-700"
        : "text-gray-700";
  return <span className={cls}>{formatPct(rate)}</span>;
}

function HealthRow({ health }: { health: WorkflowHealth }) {
  const { workflow, latest, p50DurationMs, flakeRate, sampleSize, quarantine } =
    health;
  return (
    <tr className="border-b border-gray-200">
      <td className="px-2 py-1 text-xs">
        <StatusPill status={health.status} />
      </td>
      <td className="px-2 py-1 text-xs">
        <a
          href={workflow.htmlUrl}
          className="font-medium text-gray-900 hover:underline"
          target="_blank"
          rel="noreferrer"
        >
          {workflow.name}
        </a>
        <div className="font-mono text-[10px] text-gray-500">
          {workflow.filename}
        </div>
      </td>
      <td className="px-2 py-1 text-xs">{formatMs(p50DurationMs)}</td>
      <td className="px-2 py-1 text-xs">
        <FlakeCell rate={flakeRate} />
      </td>
      <td className="px-2 py-1 text-xs text-gray-500">{sampleSize}</td>
      <td className="px-2 py-1 text-xs">
        {latest ? (
          <a
            href={latest.htmlUrl}
            className="text-gray-700 hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            {formatTimestamp(latest.createdAt)}
          </a>
        ) : (
          "—"
        )}
      </td>
      <td className="px-2 py-1 text-xs">
        {quarantine ? (
          <span
            className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-900"
            title={`reason: ${quarantine.reason}\nowner: ${quarantine.owner}`}
          >
            quarantine → {quarantine.deadline}
          </span>
        ) : (
          ""
        )}
      </td>
    </tr>
  );
}

export default async function OpsCIPage() {
  const dashboard = await getCIDashboard();
  const { workflows, quarantine, configured, reason, generatedAt, repo } =
    dashboard;

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-4">
        <p className="text-xs text-gray-500">
          <Link href="/ops" className="underline">
            ← Ops
          </Link>
        </p>
        <h1 className="text-2xl font-semibold">CI health</h1>
        <p className="mt-1 text-sm text-gray-600">
          Per-workflow status, p50 wall time, and 30-run flake rate for
          the firm's GitHub Actions surface. Pulled from the GitHub
          REST API at render time using{" "}
          <code className="font-mono text-xs">GITHUB_DISPATCH_TOKEN</code>.
          Quarantined workflows are flagged inline; see{" "}
          <code className="font-mono text-xs">.github/workflows/_quarantine.md</code>{" "}
          for the policy.
        </p>
        <p className="mt-2 text-xs text-gray-500">
          repo:{" "}
          <code className="font-mono">{repo}</code> · refreshed{" "}
          {formatTimestamp(generatedAt)}
        </p>
      </header>

      {!configured ? (
        <section className="rounded border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-semibold">CI dashboard is not wired up.</p>
          <p className="mt-1">{reason}</p>
          <p className="mt-2 text-xs">
            Set{" "}
            <code className="font-mono">GITHUB_DISPATCH_TOKEN</code>{" "}
            (a fine-grained PAT with{" "}
            <code className="font-mono">actions:read</code> on{" "}
            <code className="font-mono">{repo}</code>) on the deploy and
            reload. The token is the same one used by{" "}
            <code className="font-mono">triggerNoosphereProcessing</code>;
            the Actions read scope is additive and harmless.
          </p>
        </section>
      ) : (
        <>
          {quarantine.length > 0 && (
            <section className="mb-4 rounded border border-amber-400 bg-amber-50 p-3">
              <h2 className="text-sm font-semibold text-amber-900">
                {quarantine.length} workflow{quarantine.length === 1 ? "" : "s"}{" "}
                in quarantine
              </h2>
              <p className="mt-1 text-xs text-amber-900">
                Quarantined workflows still run but do not block PR
                merges. The fix-or-remove deadline is 14 days from
                entry; past the deadline the workflow is restored to
                blocking or deleted.
              </p>
              <ul className="mt-2 space-y-1 text-xs text-amber-900">
                {quarantine.map((q) => (
                  <li key={q.workflow}>
                    <code className="font-mono">{q.workflow}</code> —{" "}
                    {q.reason} <span className="text-amber-700">
                      (owner: {q.owner}, deadline: {q.deadline}, observed
                      failure rate: {formatPct(q.failureRate)})
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            {workflows.length === 0 ? (
              <p className="text-sm text-gray-600">
                The GitHub API returned zero runnable workflows. This
                usually means the token's repo is wrong, or the repo
                has no <code>.github/workflows/</code> directory yet.
              </p>
            ) : (
              <table className="w-full border-collapse text-left">
                <thead className="border-b border-gray-300">
                  <tr>
                    <th className="px-2 py-1 text-xs">status</th>
                    <th className="px-2 py-1 text-xs">workflow</th>
                    <th
                      className="px-2 py-1 text-xs"
                      title="Median wall-clock time across recent successful runs"
                    >
                      p50 wall
                    </th>
                    <th
                      className="px-2 py-1 text-xs"
                      title="Fraction of recent completed runs whose conclusion was 'failure'"
                    >
                      flake
                    </th>
                    <th className="px-2 py-1 text-xs" title="Completed runs sampled">
                      n
                    </th>
                    <th className="px-2 py-1 text-xs">last run</th>
                    <th className="px-2 py-1 text-xs">notes</th>
                  </tr>
                </thead>
                <tbody>
                  {workflows.map((h) => (
                    <HealthRow key={h.workflow.id} health={h} />
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </main>
  );
}
