import type { Metadata } from "next";

import { rigorDashboard } from "@/lib/api/round3";

export const metadata: Metadata = {
  title: "Rigor dashboard",
};

export default function RigorDashboardPage() {
  const months = rigorDashboard();

  return (
    <main className="container">
      <h1 style={{ fontSize: "1.35rem", marginTop: 0 }}>Rigor dashboard</h1>
      <p className="muted" style={{ maxWidth: "70ch" }}>
        Monthly pass/fail summary for the pipeline&rsquo;s quality gates. This is a transparency
        view of how many conclusion candidates pass or fail the automated and manual review stages.
      </p>

      {months.length === 0 ? (
        <p className="muted">No rigor data published yet.</p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: "1.25rem 0 0",
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
          }}
        >
          {months.map((m) => {
            const total = m.passCount + m.failCount;
            const passRate = total > 0 ? ((m.passCount / total) * 100).toFixed(0) : "\u2014";
            return (
              <li key={m.month} className="card">
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    flexWrap: "wrap",
                    gap: "0.75rem",
                  }}
                >
                  <h2 style={{ fontSize: "1.05rem", margin: 0 }}>{m.month}</h2>
                  <div className="muted" style={{ fontSize: "0.85rem" }}>
                    {passRate}% pass rate ({m.passCount} pass, {m.failCount} fail)
                  </div>
                </div>
                {m.topFailureCategories.length > 0 ? (
                  <div style={{ marginTop: "0.65rem" }}>
                    <div className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.35rem" }}>
                      Top failure categories
                    </div>
                    <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                      {m.topFailureCategories.map((cat) => (
                        <li key={cat.category} style={{ margin: "0.25rem 0", fontSize: "0.95rem" }}>
                          {cat.category} <span className="muted">({cat.count})</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
