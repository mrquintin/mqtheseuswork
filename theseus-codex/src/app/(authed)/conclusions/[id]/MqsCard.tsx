import type { MqsRecord } from "@/lib/methodologyProfiles";

const RADIAL_SIZE = 180;
const RADIAL_CENTER = RADIAL_SIZE / 2;
const RADIAL_RING = RADIAL_SIZE / 2 - 14;

type Axis = {
  key: keyof Pick<
    MqsRecord,
    | "progressivity"
    | "severity"
    | "aimMethodFit"
    | "compressibility"
    | "domainSensitivity"
  >;
  label: string;
};

const AXES: ReadonlyArray<Axis> = [
  { key: "progressivity", label: "Progressivity" },
  { key: "severity", label: "Severity" },
  { key: "aimMethodFit", label: "Aim–Method Fit" },
  { key: "compressibility", label: "Compressibility" },
  { key: "domainSensitivity", label: "Domain Sensitivity" },
];

function pct(n: number) {
  return `${Math.round(Math.max(0, Math.min(1, n)) * 100)}%`;
}

function axisPoint(index: number, total: number, scale: number) {
  // Top axis is index 0; rotate clockwise.
  const theta = -Math.PI / 2 + (index * 2 * Math.PI) / total;
  const x = RADIAL_CENTER + Math.cos(theta) * RADIAL_RING * scale;
  const y = RADIAL_CENTER + Math.sin(theta) * RADIAL_RING * scale;
  return { x, y };
}

function radialPolygon(values: number[]): string {
  return values
    .map((value, idx) => {
      const { x, y } = axisPoint(idx, values.length, Math.max(0, Math.min(1, value)));
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function evidenceLines(evidence: unknown): string[] {
  if (!evidence || typeof evidence !== "object" || Array.isArray(evidence)) return [];
  const out: string[] = [];
  for (const [key, value] of Object.entries(evidence as Record<string, unknown>)) {
    if (value === null || value === undefined) continue;
    if (typeof value === "string") {
      if (!value.trim()) continue;
      out.push(`${key}: ${value.length > 220 ? value.slice(0, 217) + "…" : value}`);
    } else if (typeof value === "number" || typeof value === "boolean") {
      out.push(`${key}: ${value}`);
    } else {
      out.push(`${key}: ${JSON.stringify(value).slice(0, 220)}`);
    }
  }
  return out;
}

export default function MqsCard({ mqs }: { mqs: MqsRecord }) {
  const values = AXES.map((a) => Number(mqs[a.key]));

  return (
    <section
      className="portal-card"
      aria-labelledby="mqs-card-title"
      style={{
        padding: "1rem 1.25rem",
        marginBottom: "1.5rem",
        display: "grid",
        gap: "0.85rem",
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h2
            className="mono"
            id="mqs-card-title"
            style={{
              color: "var(--amber-dim)",
              fontSize: "0.62rem",
              letterSpacing: "0.22em",
              margin: 0,
              textTransform: "uppercase",
            }}
          >
            Methodology Quality Score
          </h2>
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.78rem", margin: "0.35rem 0 0" }}>
            The five working criteria from the meta-method, scored for this conclusion.
            Domain sensitivity acts as a gate on the composite.
          </p>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ color: "var(--gold)", fontSize: "1.6rem", fontFamily: "'Cinzel', serif" }}>
            {pct(mqs.composite)}
          </div>
          <div className="mono" style={{ fontSize: "0.6rem", color: "var(--parchment-dim)", letterSpacing: "0.18em", textTransform: "uppercase" }}>
            Composite
          </div>
        </div>
      </header>

      <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap", alignItems: "center" }}>
        <svg
          aria-hidden="true"
          height={RADIAL_SIZE}
          role="img"
          viewBox={`0 0 ${RADIAL_SIZE} ${RADIAL_SIZE}`}
          width={RADIAL_SIZE}
        >
          {[0.25, 0.5, 0.75, 1].map((scale) => (
            <polygon
              fill="none"
              key={`grid-${scale}`}
              points={radialPolygon(AXES.map(() => scale))}
              stroke="var(--border)"
              strokeWidth={0.5}
            />
          ))}
          {AXES.map((axis, idx) => {
            const end = axisPoint(idx, AXES.length, 1);
            return (
              <line
                key={`axis-${axis.key}`}
                stroke="var(--border)"
                strokeWidth={0.5}
                x1={RADIAL_CENTER}
                x2={end.x}
                y1={RADIAL_CENTER}
                y2={end.y}
              />
            );
          })}
          <polygon
            fill="rgba(212, 175, 55, 0.15)"
            points={radialPolygon(values)}
            stroke="var(--gold)"
            strokeWidth={1.25}
          />
        </svg>

        <ul
          aria-label="MQS sub-scores"
          style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "0.35rem", minWidth: "12rem" }}
        >
          {AXES.map((axis) => {
            const v = Number(mqs[axis.key]);
            return (
              <li
                key={axis.key}
                style={{ display: "flex", justifyContent: "space-between", gap: "1rem", fontSize: "0.82rem" }}
              >
                <span style={{ color: "var(--parchment)" }}>{axis.label}</span>
                <span className="mono" style={{ color: "var(--gold)", letterSpacing: "0.05em" }}>
                  {pct(v)}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <details style={{ borderTop: "1px solid var(--border)", paddingTop: "0.65rem" }}>
        <summary
          className="mono"
          style={{
            cursor: "pointer",
            color: "var(--parchment-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Evidence (rubric trace)
        </summary>
        <div style={{ marginTop: "0.5rem", display: "grid", gap: "0.6rem" }}>
          {AXES.map((axis) => {
            const sub = (mqs.evidence as Record<string, unknown>)[axis.key];
            const lines = evidenceLines(sub);
            return (
              <div key={`evidence-${axis.key}`}>
                <h3
                  className="mono"
                  style={{
                    color: "var(--amber-dim)",
                    fontSize: "0.55rem",
                    letterSpacing: "0.18em",
                    margin: 0,
                    textTransform: "uppercase",
                  }}
                >
                  {axis.label}
                </h3>
                {lines.length === 0 ? (
                  <p style={{ margin: "0.2rem 0 0", color: "var(--parchment-dim)", fontSize: "0.72rem" }}>
                    No evidence recorded.
                  </p>
                ) : (
                  <ul style={{ margin: "0.2rem 0 0", paddingLeft: "1rem", color: "var(--parchment)", fontSize: "0.78rem" }}>
                    {lines.map((line, i) => (
                      <li key={`${axis.key}-${i}`} style={{ marginBottom: "0.15rem" }}>
                        {line}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.7rem", margin: 0 }}>
            Scored {new Date(mqs.scoredAt).toISOString().slice(0, 10)} ·{" "}
            <span className="mono">{mqs.modelName}</span> · prompt {mqs.promptVersion}
          </p>
        </div>
      </details>
    </section>
  );
}
