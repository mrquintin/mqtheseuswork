import { redirect } from "next/navigation";
import Link from "next/link";
import { getFounder } from "@/lib/auth";
import { fetchEvalRuns, toCSV, downloadHref } from "@/lib/api/round3";

function statusColor(status: string): string {
  switch (status) {
    case "passed": return "var(--gold)";
    case "failed": return "var(--ember)";
    case "running": return "var(--parchment)";
    default: return "var(--parchment-dim)";
  }
}

export default async function EvalPage() {
  const founder = await getFounder();
  if (!founder) redirect("/login");

  const runs = await fetchEvalRuns();
  const csvData = toCSV(
    runs.map((r) => ({
      id: r.id,
      name: r.name,
      status: r.status,
      passRate: r.passRate,
      startedAt: r.startedAt,
      completedAt: r.completedAt ?? "",
    })),
  );

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Evaluation runs
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1rem", fontSize: "0.9rem" }}>
        Automated evaluation suites that test the coherence and accuracy of the knowledge graph.
      </p>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <a
          href={downloadHref(csvData, "text/csv")}
          download="eval-runs.csv"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download CSV
        </a>
        <a
          href={downloadHref(JSON.stringify(runs, null, 2), "application/json")}
          download="eval-runs.json"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {runs.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No evaluation runs recorded yet. Trigger an eval run from the CLI to see results here.
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              {["Name", "Status", "Pass rate", "Started", ""].map((h) => (
                <th
                  key={h}
                  style={{
                    textAlign: "left",
                    padding: "0.5rem 0.75rem",
                    fontFamily: "'Cinzel', serif",
                    fontSize: "0.65rem",
                    color: "var(--gold-dim)",
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "0.6rem 0.75rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
                  {run.name}
                </td>
                <td style={{ padding: "0.6rem 0.75rem", color: statusColor(run.status), fontSize: "0.75rem", textTransform: "uppercase" }}>
                  {run.status}
                </td>
                <td style={{ padding: "0.6rem 0.75rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
                  {(run.passRate * 100).toFixed(1)}%
                </td>
                <td style={{ padding: "0.6rem 0.75rem", color: "var(--parchment-dim)", fontSize: "0.75rem" }}>
                  {run.startedAt ? run.startedAt.slice(0, 16) : ""}
                </td>
                <td style={{ padding: "0.6rem 0.75rem" }}>
                  <Link
                    href={`/eval/runs/${run.id}`}
                    style={{ color: "var(--gold)", fontSize: "0.75rem", textDecoration: "none" }}
                  >
                    Detail →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
