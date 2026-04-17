import { redirect, notFound } from "next/navigation";
import Link from "next/link";
import { getFounder } from "@/lib/auth";
import { fetchEvalRunDetail, toCSV, downloadHref } from "@/lib/api/round3";

export default async function EvalRunDetailPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const founder = await getFounder();
  if (!founder) redirect("/login");

  const { runId } = await params;
  const run = await fetchEvalRunDetail(runId);
  if (!run) notFound();

  const csvData = toCSV(
    run.cases.map((c) => ({
      id: c.id,
      input: c.input,
      expected: c.expected,
      actual: c.actual,
      passed: c.passed,
      notes: c.notes,
    })),
  );

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <Link href="/eval" style={{ color: "var(--gold-dim)", fontSize: "0.75rem", textDecoration: "none" }}>
        ← Back to eval runs
      </Link>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
          marginTop: "1rem",
        }}
      >
        {run.name}
      </h1>
      <div style={{ display: "flex", gap: "1.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.8rem", color: run.status === "passed" ? "var(--gold)" : "var(--ember)" }}>
          {run.status.toUpperCase()}
        </span>
        <span style={{ fontSize: "0.8rem", color: "var(--parchment-dim)" }}>
          Pass rate: {(run.passRate * 100).toFixed(1)}%
        </span>
        <span style={{ fontSize: "0.8rem", color: "var(--parchment-dim)" }}>
          {run.cases.length} cases
        </span>
      </div>
      {run.summary && (
        <p style={{ color: "var(--parchment)", marginBottom: "1rem", fontSize: "0.9rem" }}>
          {run.summary}
        </p>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <a
          href={downloadHref(csvData, "text/csv")}
          download={`eval-${runId.slice(0, 8)}.csv`}
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download CSV
        </a>
        <a
          href={downloadHref(JSON.stringify(run, null, 2), "application/json")}
          download={`eval-${runId.slice(0, 8)}.json`}
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {run.cases.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No test cases recorded for this run.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {run.cases.map((c) => (
            <li
              key={c.id}
              className="portal-card"
              style={{
                padding: "1rem 1.25rem",
                borderLeft: `3px solid ${c.passed ? "var(--gold)" : "var(--ember)"}`,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
                  case {c.id.slice(0, 8)}…
                </span>
                <span style={{ fontSize: "0.65rem", color: c.passed ? "var(--gold)" : "var(--ember)" }}>
                  {c.passed ? "PASSED" : "FAILED"}
                </span>
              </div>
              <div style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>
                <div style={{ color: "var(--parchment-dim)" }}>
                  <strong>Input:</strong>{" "}
                  <span style={{ color: "var(--parchment)" }}>{c.input}</span>
                </div>
                <div style={{ color: "var(--parchment-dim)", marginTop: "0.25rem" }}>
                  <strong>Expected:</strong>{" "}
                  <span style={{ color: "var(--parchment)" }}>{c.expected}</span>
                </div>
                <div style={{ color: "var(--parchment-dim)", marginTop: "0.25rem" }}>
                  <strong>Actual:</strong>{" "}
                  <span style={{ color: c.passed ? "var(--parchment)" : "var(--ember)" }}>{c.actual}</span>
                </div>
              </div>
              {c.notes && (
                <p style={{ marginTop: "0.35rem", fontSize: "0.75rem", color: "var(--parchment-dim)" }}>
                  {c.notes}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
