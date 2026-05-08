import Link from "next/link";

import { fetchPeerReviewsDiag, type Finding } from "@/lib/api/round3";
import { severityColor } from "@/lib/colors";

/**
 * Geometric blindspots panel.
 *
 * Surfaces the unengaged neighbors found by the
 * `geometric_blindspot` reviewer (see
 * `noosphere/peer_review/geometric_blindspot.py`). The panel deliberately
 * coexists with the prompt-driven blindspot reviewer's findings rather
 * than merging the two — provenance survives.
 *
 * The mini embedding-explorer canvas is a stylised 2D projection (not
 * the production explorer): the conclusion is at the origin, engaged
 * citations sit close along the upper arc, and unengaged neighbors are
 * placed on the lower arc with their distance modulated by the
 * predicted-contradiction distance the detector reported. The intent
 * is to make "the conclusion didn't engage these claims" visually
 * legible at a glance; the source-of-truth remains the evidence list.
 */

const REVIEWER_NAME = "geometric_blindspot";

type BlindspotRow = {
  unengagedClaimId: string;
  sparsity: number | null;
  cosineSimilarity: number | null;
  predictedDistance: number | null;
  cascadeWeight: number | null;
  contradictionScore: number | null;
  combinedScore: number | null;
  severityLabel: string | null;
  severityValue: number | null;
  finding: Finding;
};

function parseEvidence(evidence: string[] | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of evidence || []) {
    const eq = line.indexOf("=");
    if (eq <= 0) continue;
    out[line.slice(0, eq)] = line.slice(eq + 1);
  }
  return out;
}

function asNumber(value: string | undefined): number | null {
  if (value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function parseSeverity(
  raw: string | undefined,
): { label: string | null; value: number | null } {
  if (!raw) return { label: null, value: null };
  const colon = raw.indexOf(":");
  if (colon < 0) return { label: raw, value: null };
  return {
    label: raw.slice(0, colon),
    value: asNumber(raw.slice(colon + 1)),
  };
}

function rowsFromFindings(findings: Finding[]): BlindspotRow[] {
  const rows: BlindspotRow[] = [];
  for (const finding of findings) {
    if (finding.category !== "geometric_blindspot") continue;
    const ev = parseEvidence(finding.evidence);
    const severity = parseSeverity(ev["severity"]);
    rows.push({
      unengagedClaimId: ev["unengaged_claim_id"] ?? "(unknown)",
      sparsity: asNumber(ev["sparsity"]),
      cosineSimilarity: asNumber(ev["cosine_similarity"]),
      predictedDistance: asNumber(ev["predicted_distance"]),
      cascadeWeight: asNumber(ev["cascade_weight"]),
      contradictionScore: asNumber(ev["contradiction_score"]),
      combinedScore: asNumber(ev["combined_score"]),
      severityLabel: severity.label,
      severityValue: severity.value,
      finding,
    });
  }
  rows.sort(
    (a, b) => (b.combinedScore ?? 0) - (a.combinedScore ?? 0),
  );
  return rows;
}

export default async function BlindspotsPanel({
  conclusionId,
  organizationId,
  cascadeWeights,
}: {
  conclusionId: string;
  organizationId: string;
  /** Optional cascade weight lookup keyed by claim id, used to colour
   *  the canvas points. The detector already encodes this in the
   *  finding evidence; this prop is only a hint for the renderer. */
  cascadeWeights?: Record<string, number>;
}) {
  const { records, error } = await fetchPeerReviewsDiag(
    organizationId,
    conclusionId,
  );

  const allFindings: Finding[] = records
    .filter((r) => r.reviewerName === REVIEWER_NAME)
    .flatMap((r) => r.findings);
  const rows = rowsFromFindings(allFindings);
  const promptDrivenCount = records
    .filter((r) => r.reviewerName === "blindspot")
    .reduce((acc, r) => acc + r.findings.length, 0);

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <header
        style={{ display: "flex", alignItems: "baseline", gap: "0.6rem", flexWrap: "wrap" }}
      >
        <h2
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "0.8rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--gold)",
            margin: 0,
          }}
        >
          Geometric blindspots
        </h2>
        <span style={{ fontSize: "0.7rem", color: "var(--parchment-dim)" }}>
          {rows.length} unengaged neighbor{rows.length === 1 ? "" : "s"} surfaced by
          the contradiction-direction probe
          {promptDrivenCount > 0 ? (
            <>
              {" · "}
              <span style={{ color: "var(--amber-dim)" }}>
                {promptDrivenCount} prompt-driven blindspot
                {promptDrivenCount === 1 ? "" : "s"} listed separately
              </span>
            </>
          ) : null}
        </span>
      </header>

      <p
        style={{
          margin: 0,
          fontSize: "0.75rem",
          lineHeight: 1.5,
          color: "var(--parchment-dim)",
        }}
      >
        Each row below is a claim that sits inside the conclusion's
        predicted contradiction neighborhood and the conclusion does
        not cite it as a support, evidence, or dissent. Severity is
        the cascade-weight × contradiction-score product run through
        the standard severity rubric.{" "}
        <Link
          href="/methodology/geometric_blindspot"
          style={{ color: "var(--gold)", textDecoration: "none" }}
        >
          How this works →
        </Link>
      </p>

      {error ? (
        <details>
          <summary
            style={{ cursor: "pointer", fontSize: "0.7rem", color: "var(--ember)" }}
          >
            Query diagnostic
          </summary>
          <pre
            style={{
              fontSize: "0.65rem",
              color: "var(--parchment-dim)",
              whiteSpace: "pre-wrap",
            }}
          >
            {error}
          </pre>
        </details>
      ) : null}

      {rows.length === 0 ? (
        <p
          style={{
            padding: "0.6rem 0",
            color: "var(--parchment-dim)",
            fontSize: "0.85rem",
            margin: 0,
          }}
        >
          No geometric blindspots surfaced. Either the embedding-space
          neighborhood of this conclusion is fully engaged, or the
          reviewer has not run yet.{" "}
          <Link
            href={`/peer-review/${conclusionId}`}
            style={{ color: "var(--gold)", textDecoration: "none" }}
          >
            Run peer review →
          </Link>
        </p>
      ) : (
        <>
          <BlindspotCanvas rows={rows} cascadeWeights={cascadeWeights} />
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem",
            }}
          >
            {rows.map((row) => (
              <li
                key={row.unengagedClaimId}
                style={{
                  borderLeft: `2px solid ${severityColor(
                    row.finding.severity,
                  )}`,
                  padding: "0.55rem 0.85rem",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    gap: "0.5rem",
                    flexWrap: "wrap",
                  }}
                >
                  <Link
                    href={`/knowledge?focus=${encodeURIComponent(row.unengagedClaimId)}`}
                    style={{
                      color: "var(--parchment)",
                      fontSize: "0.85rem",
                      textDecoration: "none",
                      fontFamily: "monospace",
                    }}
                  >
                    {row.unengagedClaimId}
                  </Link>
                  <span
                    style={{
                      fontSize: "0.6rem",
                      letterSpacing: "0.12em",
                      textTransform: "uppercase",
                      color: severityColor(row.finding.severity),
                    }}
                  >
                    {row.severityLabel ?? row.finding.severity}
                    {row.severityValue != null
                      ? ` · ${row.severityValue.toFixed(2)}`
                      : ""}
                  </span>
                </div>
                <p
                  style={{
                    margin: "0.3rem 0 0",
                    fontSize: "0.78rem",
                    color: "var(--parchment-dim)",
                    lineHeight: 1.45,
                  }}
                >
                  {row.finding.detail}
                </p>
                <div
                  style={{
                    marginTop: "0.35rem",
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "0.6rem",
                    fontSize: "0.65rem",
                    color: "var(--parchment-dim)",
                    fontFamily: "monospace",
                  }}
                >
                  {row.sparsity != null ? (
                    <span>sparsity={row.sparsity.toFixed(2)}</span>
                  ) : null}
                  {row.cascadeWeight != null ? (
                    <span>cascade={row.cascadeWeight.toFixed(2)}</span>
                  ) : null}
                  {row.contradictionScore != null ? (
                    <span>contradiction={row.contradictionScore.toFixed(2)}</span>
                  ) : null}
                  {row.combinedScore != null ? (
                    <span>combined={row.combinedScore.toFixed(2)}</span>
                  ) : null}
                </div>
                {row.finding.suggestedAction ? (
                  <p
                    style={{
                      margin: "0.3rem 0 0",
                      fontSize: "0.7rem",
                      fontStyle: "italic",
                      color: "var(--gold-dim)",
                    }}
                  >
                    {row.finding.suggestedAction}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

// ── Mini embedding canvas ────────────────────────────────────────────

function hashAngle(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 360) * (Math.PI / 180);
}

function BlindspotCanvas({
  rows,
  cascadeWeights,
}: {
  rows: BlindspotRow[];
  cascadeWeights?: Record<string, number>;
}) {
  const W = 360;
  const H = 220;
  const cx = W / 2;
  const cy = H / 2;
  const baseR = 28;
  const maxR = Math.min(W, H) / 2 - 24;

  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 4,
        padding: "0.6rem",
        background: "var(--stone-light, rgba(0,0,0,0.04))",
      }}
      aria-label="Geometric blindspot canvas — conclusion at the centre, unengaged neighbors radiating outward"
    >
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        style={{ display: "block", maxHeight: "240px" }}
        role="img"
      >
        <defs>
          <radialGradient id="bs-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--gold, #d4a017)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--gold, #d4a017)" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle cx={cx} cy={cy} r={maxR} fill="url(#bs-glow)" />
        <circle
          cx={cx}
          cy={cy}
          r={baseR}
          fill="var(--gold, #d4a017)"
          opacity={0.85}
        />
        <text
          x={cx}
          y={cy + 4}
          textAnchor="middle"
          fontSize="10"
          fontFamily="'Cinzel', serif"
          fill="var(--stone, #1a1a1a)"
        >
          conclusion
        </text>
        {rows.map((row, i) => {
          const angle = hashAngle(row.unengagedClaimId) + i * 0.18;
          const distFactor = row.predictedDistance != null
            ? Math.max(0.25, Math.min(1, row.predictedDistance + 0.4))
            : 0.7;
          const r = baseR + 18 + (maxR - baseR - 22) * distFactor;
          const x = cx + Math.cos(angle) * r;
          const y = cy + Math.sin(angle) * r;
          const cw = cascadeWeights?.[row.unengagedClaimId] ?? row.cascadeWeight ?? 0.5;
          const radius = 5 + cw * 7;
          const stroke =
            row.severityLabel === "high"
              ? "var(--ember, #b53b27)"
              : row.severityLabel === "medium"
                ? "var(--amber, #d4a017)"
                : "var(--parchment-dim, #888)";
          return (
            <g key={row.unengagedClaimId}>
              <line
                x1={cx}
                y1={cy}
                x2={x}
                y2={y}
                stroke={stroke}
                strokeOpacity={0.35}
                strokeDasharray="2 3"
              />
              <circle
                cx={x}
                cy={y}
                r={radius}
                fill={stroke}
                fillOpacity={0.75}
                stroke={stroke}
              />
              <title>
                {row.unengagedClaimId} · severity={row.severityLabel ?? "?"} ·
                cascade={cw.toFixed(2)} · contradiction=
                {(row.contradictionScore ?? 0).toFixed(2)}
              </title>
            </g>
          );
        })}
      </svg>
      <p
        style={{
          margin: "0.4rem 0 0",
          fontSize: "0.65rem",
          color: "var(--parchment-dim)",
          lineHeight: 1.5,
        }}
      >
        Distance from centre tracks the predicted-contradiction distance;
        circle size tracks cascade weight; colour tracks severity. The
        canvas is a stylised projection — the production embedding
        explorer renders the actual geometry.
      </p>
    </div>
  );
}
