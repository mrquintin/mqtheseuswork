import { redirect } from "next/navigation";

import {
  type CounterfactualCell,
  findCell,
  loadCounterfactualManifest,
} from "@/lib/counterfactualReplayApi";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

type SearchParams = {
  actual?: string;
  alt?: string;
};

export default async function CounterfactualPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const params = (await searchParams) ?? {};
  const manifest = loadCounterfactualManifest();

  const focused =
    params.actual && params.alt
      ? findCell(manifest, params.actual, params.alt)
      : null;

  return (
    <main style={{ maxWidth: "1080px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Counterfactual replay — would-have-been-better
      </h1>
      <p style={{ color: "var(--parchment-dim)", maxWidth: "62ch", lineHeight: 1.55 }}>
        For every resolved forecast and every adapter-compatible alternative
        method, this is the absolute Brier difference if we had used the
        column method instead of the row method. Negative cell deltas mean
        the alternative would have done better; positive means worse. These
        numbers are private — small <code>n</code> and mismatched domain
        bounds make per-cell verdicts unreliable, so we never publish them.
      </p>
      <p style={{ color: "var(--parchment-dim)", fontSize: "0.78rem" }}>
        manifest: {manifest.source} · generated {manifest.generatedAt}
      </p>

      {manifest.source === "empty" || manifest.cells.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <Matrix manifest={manifest} active={{ actual: params.actual ?? null, alt: params.alt ?? null }} />
          {focused ? <CellDrillDown cell={focused} /> : null}
          <Legend />
        </>
      )}
    </main>
  );
}

function EmptyState() {
  return (
    <div
      className="portal-card"
      style={{ padding: "1.25rem 1.5rem", marginTop: "1.5rem", color: "var(--parchment-dim)" }}
    >
      <p style={{ margin: 0 }}>
        No counterfactual manifest on disk yet. Generate one with{" "}
        <code>noosphere replay export-manifest</code> after at least one
        resolved forecast has accrued and an alternative method's adapter
        is registered.
      </p>
    </div>
  );
}

function Matrix({
  manifest,
  active,
}: {
  manifest: ReturnType<typeof loadCounterfactualManifest>;
  active: { actual: string | null; alt: string | null };
}) {
  const actuals = manifest.actualMethods;
  const alts = manifest.alternativeMethods;
  return (
    <section style={{ marginTop: "1.5rem", overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", minWidth: "640px", width: "100%" }}>
        <thead>
          <tr>
            <th
              style={{
                textAlign: "left",
                padding: "0.5rem 0.75rem",
                fontSize: "0.72rem",
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                color: "var(--parchment-dim)",
                borderBottom: "1px solid var(--parchment-dim)",
              }}
            >
              actual ↓ / alt →
            </th>
            {alts.map((alt) => (
              <th
                key={alt}
                style={{
                  padding: "0.5rem 0.75rem",
                  fontSize: "0.72rem",
                  fontFamily: "ui-monospace, Menlo, monospace",
                  borderBottom: "1px solid var(--parchment-dim)",
                  color: "var(--parchment)",
                }}
              >
                {alt}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {actuals.map((actual) => (
            <tr key={actual}>
              <th
                scope="row"
                style={{
                  textAlign: "left",
                  padding: "0.5rem 0.75rem",
                  fontFamily: "ui-monospace, Menlo, monospace",
                  fontSize: "0.78rem",
                  color: "var(--parchment)",
                  borderBottom: "1px solid rgba(255,255,255,0.06)",
                }}
              >
                {actual}
              </th>
              {alts.map((alt) => {
                if (alt === actual) {
                  return (
                    <td
                      key={alt}
                      style={{
                        padding: "0.5rem 0.75rem",
                        textAlign: "center",
                        color: "var(--parchment-dim)",
                        borderBottom: "1px solid rgba(255,255,255,0.06)",
                      }}
                    >
                      —
                    </td>
                  );
                }
                const cell = findCell(manifest, actual, alt);
                const isActive = active.actual === actual && active.alt === alt;
                return (
                  <td
                    key={alt}
                    style={{
                      padding: "0",
                      borderBottom: "1px solid rgba(255,255,255,0.06)",
                      background: isActive ? "rgba(212,160,23,0.10)" : undefined,
                    }}
                  >
                    <Cell cell={cell} actual={actual} alt={alt} />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Cell({
  cell,
  actual,
  alt,
}: {
  cell: CounterfactualCell | null;
  actual: string;
  alt: string;
}) {
  if (!cell || cell.n === 0) {
    return (
      <a
        href={`?actual=${encodeURIComponent(actual)}&alt=${encodeURIComponent(alt)}`}
        style={{
          display: "block",
          padding: "0.55rem 0.75rem",
          textAlign: "center",
          color: "var(--parchment-dim)",
          textDecoration: "none",
          fontFamily: "ui-monospace, Menlo, monospace",
          fontSize: "0.78rem",
        }}
      >
        n=0
      </a>
    );
  }

  const delta = cell.meanBrierDelta;
  const better = delta < 0;
  const accent = better ? "var(--gold)" : "var(--parchment-dim)";
  const sample = sampleSizePill(cell.n);

  return (
    <a
      href={`?actual=${encodeURIComponent(actual)}&alt=${encodeURIComponent(alt)}`}
      style={{
        display: "block",
        padding: "0.55rem 0.75rem",
        textDecoration: "none",
        color: "var(--parchment)",
      }}
    >
      <div
        style={{
          fontFamily: "ui-monospace, Menlo, monospace",
          fontSize: "0.92rem",
          color: accent,
        }}
      >
        {delta >= 0 ? "+" : ""}
        {delta.toFixed(3)}
      </div>
      <div
        style={{
          fontSize: "0.66rem",
          color: "var(--parchment-dim)",
          marginTop: "0.15rem",
          letterSpacing: "0.08em",
        }}
      >
        |Δ|={cell.meanAbsBrierDelta.toFixed(3)} · {sample}
      </div>
    </a>
  );
}

function sampleSizePill(n: number): string {
  if (n < 5) return `n=${n} (sparse)`;
  if (n < 20) return `n=${n}`;
  return `n=${n} ✓`;
}

function CellDrillDown({ cell }: { cell: CounterfactualCell }) {
  return (
    <section
      className="portal-card"
      style={{ padding: "1.25rem 1.5rem", marginTop: "1.5rem" }}
      aria-labelledby="cell-drilldown-title"
    >
      <h2
        id="cell-drilldown-title"
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.06em",
          fontSize: "1.1rem",
        }}
      >
        {cell.actualMethod} → {cell.alternativeMethod}
      </h2>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          marginTop: "0.5rem",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: "0.75rem",
          fontFamily: "ui-monospace, Menlo, monospace",
          fontSize: "0.82rem",
        }}
      >
        <li>n = {cell.n}</li>
        <li>actual Brier = {cell.meanBrierActual.toFixed(3)}</li>
        <li>alt Brier = {cell.meanBrierAlternative.toFixed(3)}</li>
        <li>Δ = {cell.meanBrierDelta.toFixed(3)}</li>
        <li>|Δ| = {cell.meanAbsBrierDelta.toFixed(3)}</li>
        <li>alt better in {cell.altBetterCount} / {cell.n}</li>
      </ul>
      <h3
        style={{
          marginTop: "1.25rem",
          fontSize: "0.72rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
        }}
      >
        Worked examples
      </h3>
      {cell.examples.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.82rem" }}>
          Manifest did not include per-conclusion examples for this cell.
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, marginTop: "0.5rem" }}>
          {cell.examples.map((ex) => {
            const altBetter = ex.altBrier < ex.actualBrier;
            return (
              <li
                key={ex.conclusionId}
                style={{
                  borderTop: "1px solid rgba(255,255,255,0.08)",
                  padding: "0.55rem 0",
                  fontSize: "0.84rem",
                }}
              >
                <div style={{ display: "flex", gap: "0.5rem", justifyContent: "space-between" }}>
                  <strong style={{ flex: 1, fontWeight: 500 }}>
                    {ex.headline || ex.conclusionId}
                  </strong>
                  <span
                    style={{
                      fontFamily: "ui-monospace, Menlo, monospace",
                      color: altBetter ? "var(--gold)" : "var(--parchment-dim)",
                    }}
                  >
                    {altBetter ? "alt wins" : "actual wins"}
                  </span>
                </div>
                <div
                  style={{
                    color: "var(--parchment-dim)",
                    fontSize: "0.74rem",
                    marginTop: "0.15rem",
                    fontFamily: "ui-monospace, Menlo, monospace",
                  }}
                >
                  outcome={ex.outcome ? "YES" : "NO"} · actual p=
                  {ex.actualConfidence.toFixed(2)} (Brier {ex.actualBrier.toFixed(3)}) ·
                  alt p={ex.altConfidence.toFixed(2)} (Brier {ex.altBrier.toFixed(3)})
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Legend() {
  return (
    <section
      style={{
        marginTop: "1.5rem",
        padding: "0.85rem 1rem",
        borderLeft: "2px solid var(--gold)",
        background: "rgba(212,160,23,0.04)",
        color: "var(--parchment-dim)",
        fontSize: "0.78rem",
        lineHeight: 1.55,
      }}
    >
      <strong style={{ color: "var(--parchment)" }}>How to read the matrix.</strong>{" "}
      Each cell scores the alternative method on the same realized
      outcomes the row method handled, using only inputs that were
      visible at each conclusion's <code>created_at</code> (no
      anachronism). Sample-size pills mark sparse rows; do not infer
      that the lowest cell is the method we should switch to — domain
      bounds and input shapes vary across methods, and "better here on
      n=4" does not generalize. This page exists to surface candidate
      questions, not verdicts.
    </section>
  );
}
