import type { Metadata } from "next";

import { allDecayStats } from "@/lib/api/round3";

export const metadata: Metadata = {
  title: "Decay statistics",
};

export default function DecayStatsPage() {
  const stats = allDecayStats();

  return (
    <main className="container">
      <h1 style={{ fontSize: "1.35rem", marginTop: 0 }}>Confidence decay statistics</h1>
      <p className="muted" style={{ maxWidth: "70ch" }}>
        Aggregated decay statistics for published conclusions. Confidence decays over time as new
        evidence accumulates or calibration adjustments are applied.
      </p>

      {stats.length === 0 ? (
        <p className="muted">No decay data published yet.</p>
      ) : (
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            marginTop: "1.25rem",
            fontSize: "0.95rem",
          }}
        >
          <thead>
            <tr style={{ borderBottom: "2px solid var(--border)" }}>
              <th style={{ textAlign: "left", padding: "0.5rem 0.75rem", fontWeight: 600 }}>Conclusion</th>
              <th style={{ textAlign: "right", padding: "0.5rem 0.75rem", fontWeight: 600 }}>Original</th>
              <th style={{ textAlign: "right", padding: "0.5rem 0.75rem", fontWeight: 600 }}>Current</th>
              <th style={{ textAlign: "right", padding: "0.5rem 0.75rem", fontWeight: 600 }}>Rate</th>
              <th style={{ textAlign: "right", padding: "0.5rem 0.75rem", fontWeight: 600 }}>Events</th>
              <th style={{ textAlign: "left", padding: "0.5rem 0.75rem", fontWeight: 600 }}>Last event</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((s) => (
              <tr key={s.conclusionId} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "0.5rem 0.75rem" }}>
                  <code style={{ fontSize: "0.85rem" }}>{s.slug}</code>
                </td>
                <td style={{ padding: "0.5rem 0.75rem", textAlign: "right" }}>
                  {(s.originalConfidence * 100).toFixed(0)}%
                </td>
                <td style={{ padding: "0.5rem 0.75rem", textAlign: "right" }}>
                  {(s.currentConfidence * 100).toFixed(0)}%
                </td>
                <td style={{ padding: "0.5rem 0.75rem", textAlign: "right" }} className="muted">
                  {s.decayRate.toFixed(3)}/period
                </td>
                <td style={{ padding: "0.5rem 0.75rem", textAlign: "right" }}>{s.totalDecayEvents}</td>
                <td style={{ padding: "0.5rem 0.75rem" }} className="muted">
                  {s.lastDecayEvent.slice(0, 10)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
