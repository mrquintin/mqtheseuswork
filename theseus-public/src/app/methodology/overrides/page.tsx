import type { Metadata } from "next";

import { allOverrides } from "@/lib/api/round3";

export const metadata: Metadata = {
  title: "Founder overrides",
};

export default function OverridesPage() {
  const overrides = allOverrides();

  return (
    <main className="container">
      <h1 style={{ fontSize: "1.35rem", marginTop: 0 }}>Founder overrides</h1>
      <p className="muted" style={{ maxWidth: "70ch" }}>
        Every founder override is published with full justification. Overrides are manual
        corrections applied to pipeline outputs when the founder determines the automated result is
        inadequate.
      </p>

      {overrides.length === 0 ? (
        <p className="muted">No overrides issued.</p>
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
          {overrides.map((o) => (
            <li key={o.id} className="card">
              <div className="muted" style={{ fontSize: "0.85rem" }}>
                {o.issuedAt.slice(0, 10)} &middot; {o.issuedBy} &middot; conclusion {o.conclusionId}
              </div>
              <div style={{ marginTop: "0.5rem" }}>
                <strong>Field:</strong> {o.field}
              </div>
              <div style={{ marginTop: "0.35rem", fontSize: "0.95rem" }}>
                <span className="muted">Original:</span> {o.originalValue}
                <span style={{ margin: "0 0.5rem" }}>&rarr;</span>
                <span className="muted">Override:</span> {o.overriddenValue}
              </div>
              <div style={{ marginTop: "0.65rem" }}>
                <div className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.25rem" }}>
                  Justification
                </div>
                <p style={{ margin: 0, fontSize: "0.95rem" }}>{o.justification}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
