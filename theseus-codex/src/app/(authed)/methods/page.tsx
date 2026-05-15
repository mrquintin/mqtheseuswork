import fs from "node:fs";
import path from "node:path";
import { redirect } from "next/navigation";
import Link from "next/link";
import { fetchMethods, toCSV, downloadHref } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";
import SeverityReliabilityPlot, {
  type SeverityReliabilityBin,
} from "@/components/SeverityReliabilityPlot";

// ── Severity calibration artifact (Round 17 prompt 22) ───────────────
//
// The nightly `noosphere/scripts/fit_severity_model.sh` job calibrates
// the severity rubric against realized objection outcomes and writes a
// `model.json` artifact. The methods page surfaces its reliability
// diagram and cold-start state. Missing artifact → the section renders
// a "not yet run" note rather than erroring — the model is an aid, and
// a missing artifact is a silent no-op.

type SeverityCalibrationArtifact = {
  status: "fitted" | "cold_start";
  generated_at: string;
  n_labeled: number;
  n_material: number;
  n_addendum: number;
  n_dismissed: number;
  min_n: number;
  cold_start_reason: string;
  model: {
    trained_at: string;
    n_train: number;
    base_rate: number;
  } | null;
  evaluation: {
    n_eval: number;
    skill: number;
    beats_baseline: boolean;
    auc: number;
    brier: number;
    accuracy: number;
  } | null;
  reliability: Array<{
    lo: number;
    hi: number;
    n: number;
    mean_predicted: number | null;
    realized_change_rate: number | null;
    sparse: boolean;
  }>;
  rescore?: {
    n_conclusions: number;
    n_founder_queue: number;
    delta: number;
  };
};

function readSeverityCalibrationArtifact(): SeverityCalibrationArtifact | null {
  const candidates = [
    path.join(
      process.cwd(),
      "..",
      "noosphere_data",
      "severity_calibration",
      "model.json",
    ),
    path.join(
      process.cwd(),
      "public",
      "severity_calibration",
      "model.json",
    ),
  ];
  for (const p of candidates) {
    try {
      return JSON.parse(
        fs.readFileSync(p, "utf8"),
      ) as SeverityCalibrationArtifact;
    } catch {
      // try next
    }
  }
  return null;
}

function SeverityCalibrationSection() {
  const artifact = readSeverityCalibrationArtifact();

  const heading = (
    <div style={{ marginTop: "2.5rem", marginBottom: "0.75rem" }}>
      <div
        style={{
          fontSize: "0.6rem",
          color: "var(--gold-dim, var(--gold))",
          textTransform: "uppercase",
          letterSpacing: "0.1em",
        }}
      >
        Round 17 · prompt 22
      </div>
      <h2
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.06em",
          fontSize: "1rem",
          margin: "0.2rem 0 0",
        }}
      >
        Severity calibration
      </h2>
      <p
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.82rem",
          margin: "0.3rem 0 0",
        }}
      >
        Does the severity rubric predict which objections, if true,
        actually change the conclusion? The nightly fit checks the
        stipulated formula against realized revision outcomes.
      </p>
    </div>
  );

  if (!artifact) {
    return (
      <section>
        {heading}
        <div
          className="portal-card"
          style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)", fontSize: "0.82rem" }}
        >
          No severity-calibration artifact yet. Run{" "}
          <code>noosphere/scripts/fit_severity_model.sh</code> — it
          labels recorded objections by their realized outcome and fits
          (or, on a thin corpus, deliberately defers) the calibration
          model.
        </div>
      </section>
    );
  }

  const coldStart = artifact.status === "cold_start";
  const accent = coldStart
    ? "var(--parchment-dim)"
    : artifact.evaluation && !artifact.evaluation.beats_baseline
      ? "var(--ember)"
      : "rgba(160, 211, 170, 0.9)";

  const bins: SeverityReliabilityBin[] = artifact.reliability.map((b) => ({
    lo: b.lo,
    hi: b.hi,
    n: b.n,
    meanPredicted: b.mean_predicted,
    realizedChangeRate: b.realized_change_rate,
    sparse: b.sparse,
  }));

  return (
    <section>
      {heading}
      <div
        className="portal-card"
        style={{ padding: "1rem 1.25rem", borderLeft: `3px solid ${accent}` }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "0.5rem",
            alignItems: "baseline",
          }}
        >
          <span
            style={{
              fontSize: "0.65rem",
              color: accent,
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              fontWeight: 600,
            }}
          >
            {coldStart ? "Cold start — deferred" : "Fitted model active"}
          </span>
          <span style={{ fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
            {artifact.n_labeled} labelled · {artifact.n_material} material ·{" "}
            {artifact.n_addendum} addendum · {artifact.n_dismissed} dismissed
          </span>
        </div>

        {coldStart ? (
          <p
            style={{
              marginTop: "0.5rem",
              color: "var(--parchment)",
              fontSize: "0.82rem",
              lineHeight: 1.55,
            }}
          >
            {artifact.cold_start_reason} The stipulated rubric stays the
            active scorer; the replacement engages automatically at{" "}
            {artifact.min_n} labelled objections. This is deliberate — a
            noisy model fit on tiny data is worse than the honest formula.
          </p>
        ) : (
          <>
            <div
              style={{
                marginTop: "0.6rem",
                display: "flex",
                gap: "1.25rem 2rem",
                flexWrap: "wrap",
                fontSize: "0.78rem",
                color: "var(--parchment)",
              }}
            >
              {artifact.evaluation && (
                <>
                  <span>
                    Held-out skill{" "}
                    <strong style={{ color: accent }}>
                      {artifact.evaluation.skill >= 0 ? "+" : ""}
                      {(artifact.evaluation.skill * 100).toFixed(0)}%
                    </strong>
                    {!artifact.evaluation.beats_baseline &&
                      " — no skill, treat as noise"}
                  </span>
                  <span>
                    AUC{" "}
                    <strong>{artifact.evaluation.auc.toFixed(3)}</strong>
                  </span>
                  <span>
                    Brier{" "}
                    <strong>{artifact.evaluation.brier.toFixed(3)}</strong>
                  </span>
                  <span>
                    Held-out n{" "}
                    <strong>{artifact.evaluation.n_eval}</strong>
                  </span>
                </>
              )}
              {artifact.rescore && (
                <span>
                  Founder queue{" "}
                  <strong style={{ color: "var(--amber)" }}>
                    {artifact.rescore.n_founder_queue}
                  </strong>{" "}
                  / {artifact.rescore.n_conclusions} re-scored (δ&gt;
                  {artifact.rescore.delta})
                </span>
              )}
            </div>
            <div style={{ marginTop: "1rem", maxWidth: "460px" }}>
              <SeverityReliabilityPlot bins={bins} />
            </div>
          </>
        )}

        <div
          style={{
            marginTop: "0.75rem",
            fontSize: "0.62rem",
            color: "var(--parchment-dim)",
          }}
        >
          generated {artifact.generated_at.slice(0, 16)} ·{" "}
          see <code>docs/methods/Severity_Calibration_Status.md</code>
        </div>
      </div>
    </section>
  );
}

export default async function MethodsPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const methods = await fetchMethods(tenant.organizationId);
  const csvData = toCSV(
    methods.map((m) => ({
      name: m.name,
      latestVersion: m.latestVersion,
      status: m.status,
      usageCount: m.usageCount,
      drift: m.driftState,
      driftLastObservedAt: m.driftLastObservedAt ?? "",
      description: m.description,
    })),
  );

  function statusColor(status: string): string {
    switch (status) {
      case "active": return "var(--gold)";
      case "candidate": return "var(--parchment)";
      case "deprecated": return "var(--parchment-dim)";
      default: return "var(--parchment-dim)";
    }
  }

  function driftColor(state: string): string {
    switch (state) {
      case "escalate":
        return "var(--ember, #c0392b)";
      case "warn":
        return "var(--amber, #d4a017)";
      case "insufficient":
        return "var(--parchment-dim)";
      case "ok":
        return "var(--parchment-dim)";
      default:
        return "var(--parchment-dim)";
    }
  }

  function driftLabel(state: string): string {
    switch (state) {
      case "escalate":
        return "DRIFT — escalate";
      case "warn":
        return "DRIFT — warn";
      case "insufficient":
        return "n < 8";
      case "ok":
        return "stable";
      default:
        return "—";
    }
  }

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Methods registry
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "0.75rem", fontSize: "0.9rem" }}>
        Registered extraction and analysis methods with versioned documentation.
      </p>

      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        <Link href="/methods/candidates" className="btn" style={{ fontSize: "0.65rem", textDecoration: "none" }}>
          View candidates
        </Link>
        <a
          href={downloadHref(csvData, "text/csv")}
          download="methods.csv"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download CSV
        </a>
        <a
          href={downloadHref(JSON.stringify(methods, null, 2), "application/json")}
          download="methods.json"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Download JSON
        </a>
      </div>

      {methods.length === 0 ? (
        <div className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
          No methods registered yet. Methods are added when extraction pipelines are configured.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {methods.map((m) => {
            const driftActive = m.driftState === "warn" || m.driftState === "escalate";
            return (
              <li
                key={m.name}
                className="portal-card"
                style={{
                  padding: "1rem 1.25rem",
                  borderLeft: driftActive
                    ? `3px solid ${driftColor(m.driftState)}`
                    : undefined,
                  background: driftActive
                    ? "rgba(192, 57, 43, 0.04)"
                    : undefined,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
                  <Link
                    href={`/methods/${encodeURIComponent(m.name)}/${encodeURIComponent(m.latestVersion)}`}
                    style={{ color: "var(--gold)", textDecoration: "none", fontFamily: "'Cinzel', serif", fontSize: "0.85rem" }}
                  >
                    {m.name}
                  </Link>
                  <div style={{ display: "flex", gap: "0.75rem", alignItems: "baseline" }}>
                    <span
                      title={
                        m.driftLastObservedAt
                          ? `Last drift evaluation: ${m.driftLastObservedAt}`
                          : "No drift evaluation yet"
                      }
                      style={{
                        fontSize: "0.65rem",
                        color: driftColor(m.driftState),
                        textTransform: "uppercase",
                        fontWeight: driftActive ? 600 : 400,
                        letterSpacing: "0.08em",
                      }}
                    >
                      {driftLabel(m.driftState)}
                    </span>
                    <span style={{ fontSize: "0.65rem", color: statusColor(m.status), textTransform: "uppercase" }}>
                      {m.status}
                    </span>
                  </div>
                </div>
                <p style={{ marginTop: "0.35rem", color: "var(--parchment)", fontSize: "0.85rem" }}>
                  {m.description}
                </p>
                <div style={{ marginTop: "0.25rem", fontSize: "0.65rem", color: "var(--parchment-dim)" }}>
                  v{m.latestVersion} · {m.usageCount} uses
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <SeverityCalibrationSection />
    </main>
  );
}
