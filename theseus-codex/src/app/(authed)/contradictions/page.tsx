import Link from "next/link";
import { Suspense } from "react";
import TemporalReplayBar from "@/components/TemporalReplayBar";
import CoherenceRadar from "@/components/CoherenceRadarClient";
import { db } from "@/lib/db";
import { resolveClaimTexts } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";
import { AS_OF_ISO, asOfEndUtc } from "@/lib/replayDate";
import JsonToggle from "./json-toggle";
import ContradictionActions from "./contradiction-actions";

// Six coherence layers in the order the radar component expects.
const LAYER_KEYS = [
  "s1_consistency",
  "s2_argumentation",
  "s3_probabilistic",
  "s4_geometric",
  "s5_compression",
  "s6_llm_judge",
] as const;

type LayerKey = (typeof LAYER_KEYS)[number];

const LAYER_DESCRIPTIONS: Record<
  LayerKey,
  { name: string; explanation: string }
> = {
  s1_consistency: {
    name: "Logical consistency",
    explanation:
      "Checks whether the two claims can both be true simultaneously using formal logical rules.",
  },
  s2_argumentation: {
    name: "Argumentation analysis",
    explanation:
      "Examines the argumentative structure — whether one claim undermines the premises or conclusions of the other.",
  },
  s3_probabilistic: {
    name: "Probabilistic coherence",
    explanation:
      "Measures whether believing both claims at their stated confidence levels is statistically coherent.",
  },
  s4_geometric: {
    name: "Semantic geometry",
    explanation:
      "Analyzes the geometric relationship between the claims in the embedding space — how their meaning vectors relate.",
  },
  s5_compression: {
    name: "Information compression",
    explanation:
      "Tests whether the two claims compress well together (coherent) or resist joint compression (contradictory).",
  },
  s6_llm_judge: {
    name: "LLM adjudication",
    explanation:
      "An independent language model assessment of whether these claims are in genuine tension.",
  },
};

function extractLayerValues(json: string | null): number[] {
  if (!json) return new Array(6).fill(0);
  try {
    const parsed = JSON.parse(json) as Record<string, unknown>;
    return LAYER_KEYS.map((k) => {
      const v = parsed[k];
      return typeof v === "number" && Number.isFinite(v) ? v : 0;
    });
  } catch {
    return new Array(6).fill(0);
  }
}

/**
 * The contradiction inserter currently writes `sixLayerJson` as a
 * provenance stub (e.g. `{"source": "heuristic"}` or `{"source": "llm"}`)
 * — it does NOT include per-layer coherence scores. Rendering the radar
 * against that produces an empty rotating hex with no signal. This guard
 * lets the UI fall back to a useful summary (detection method + narrative)
 * until the pipeline starts computing real layer scores per pair.
 */
function hasRealLayerScores(json: string | null): boolean {
  if (!json) return false;
  try {
    const parsed = JSON.parse(json) as Record<string, unknown>;
    return LAYER_KEYS.some(
      (k) => typeof parsed[k] === "number" && Number.isFinite(parsed[k] as number),
    );
  } catch {
    return false;
  }
}

function detectionSource(json: string | null): string | null {
  if (!json) return null;
  try {
    const parsed = JSON.parse(json) as Record<string, unknown>;
    const src = typeof parsed.source === "string" ? parsed.source : null;
    if (!src) return null;
    if (parsed.cross_upload === true) return `${src} (cross-upload)`;
    return src;
  } catch {
    return null;
  }
}

export default async function ContradictionsPage({
  searchParams,
}: {
  searchParams: Promise<{ asOf?: string; showResolved?: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const sp = await searchParams;
  const asOf = sp.asOf;
  const end = asOf && AS_OF_ISO.test(asOf) ? asOfEndUtc(asOf) : undefined;
  const showResolved = sp.showResolved === "true";

  const baseWhere = {
    organizationId: tenant.organizationId,
    ...(end ? { createdAt: { lte: end } } : {}),
  };

  const [rows, resolvedCount] = await Promise.all([
    db.contradiction.findMany({
      where: showResolved
        ? baseWhere
        : { ...baseWhere, status: "active" },
      orderBy: { severity: "desc" },
      take: 50,
    }),
    db.contradiction.count({
      where: { ...baseWhere, status: { in: ["resolved", "dismissed"] } },
    }),
  ]);

  // Batch-resolve every claim id referenced on this page so each card
  // renders with actual claim text, not opaque CUIDs.
  const allClaimIds = Array.from(
    new Set(rows.flatMap((r) => [r.claimAId, r.claimBId])),
  );
  const claimTexts = await resolveClaimTexts(tenant.organizationId, allClaimIds);

  const critical = rows.filter((r) => r.severity >= 0.7);
  const notable = rows.filter((r) => r.severity >= 0.4 && r.severity < 0.7);
  const minor = rows.filter((r) => r.severity < 0.4);

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <Suspense fallback={null}>
        <TemporalReplayBar />
      </Suspense>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Contradictions
      </h1>
      {end ? (
        <p style={{ color: "var(--ember)", fontSize: "0.85rem", marginBottom: "1rem" }}>
          Replay: rows with <code>createdAt</code> ≤ end of {asOf} (UTC).
        </p>
      ) : null}
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontStyle: "italic",
          fontSize: "1rem",
          color: "var(--parchment-dim)",
          maxWidth: "44em",
          lineHeight: 1.55,
          marginBottom: "1.5rem",
        }}
      >
        Contradictions surface when two conclusions in the model are in
        tension — they resist being held simultaneously. Each is scored by
        six independent coherence layers. High severity means the model is
        confident these claims genuinely conflict.
      </p>

      <div
        style={{
          display: "flex",
          gap: "1.5rem",
          marginBottom: "1.5rem",
          fontSize: "0.8rem",
          alignItems: "baseline",
          flexWrap: "wrap",
        }}
      >
        <span style={{ color: "var(--ember)" }}>{critical.length} critical</span>
        <span style={{ color: "var(--amber)" }}>{notable.length} notable</span>
        <span style={{ color: "var(--parchment-dim)" }}>{minor.length} minor</span>
        <span
          className="mono"
          style={{
            fontSize: "0.65rem",
            color: "var(--parchment-dim)",
            marginLeft: "auto",
          }}
        >
          {rows.length} showing
        </span>
        <Link
          href={
            showResolved
              ? "/contradictions"
              : "/contradictions?showResolved=true"
          }
          className="mono"
          style={{
            fontSize: "0.6rem",
            color: "var(--amber-dim)",
            textDecoration: "none",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
          }}
        >
          {showResolved ? "Hide resolved" : `Show resolved (${resolvedCount})`}
        </Link>
      </div>

      {rows.length === 0 ? (
        <div style={{ padding: "2rem", textAlign: "center" }}>
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontStyle: "italic",
              fontSize: "1rem",
              color: "var(--parchment)",
            }}
          >
            Concordia regnat.
          </p>
          <p
            className="mono"
            style={{
              fontSize: "0.7rem",
              color: "var(--parchment-dim)",
              marginTop: "0.25rem",
            }}
          >
            No contradictions detected — the model is internally coherent.
          </p>
        </div>
      ) : (
        <>
          {critical.length > 0 && (
            <ContradictionBand
              label={`CRITICAL · ${critical.length}`}
              rows={critical}
              claimTexts={claimTexts}
            />
          )}
          {notable.length > 0 && (
            <ContradictionBand
              label={`NOTABLE · ${notable.length}`}
              rows={notable}
              claimTexts={claimTexts}
            />
          )}
          {minor.length > 0 && (
            <ContradictionBand
              label={`MINOR · ${minor.length}`}
              rows={minor}
              claimTexts={claimTexts}
            />
          )}
        </>
      )}
    </main>
  );
}

type Row = {
  id: string;
  claimAId: string;
  claimBId: string;
  severity: number;
  sixLayerJson: string | null;
  narrative: string;
  status: string;
};

function ContradictionBand({
  label,
  rows,
  claimTexts,
}: {
  label: string;
  rows: Row[];
  claimTexts: Record<string, string>;
}) {
  return (
    <section
      className="ascii-frame"
      data-label={label}
      style={{ marginBottom: "1.5rem" }}
    >
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
        {rows.map((c) => (
          <ContradictionCard key={c.id} row={c} claimTexts={claimTexts} />
        ))}
      </ul>
    </section>
  );
}

function ContradictionCard({
  row,
  claimTexts,
}: {
  row: Row;
  claimTexts: Record<string, string>;
}) {
  const severityColor =
    row.severity >= 0.7
      ? "var(--ember)"
      : row.severity >= 0.4
      ? "var(--amber)"
      : "var(--parchment-dim)";
  const aText = claimTexts[row.claimAId];
  const bText = claimTexts[row.claimBId];

  return (
    <li
      className="portal-card"
      style={{
        padding: 0,
        overflow: "hidden",
        borderLeft: `3px solid ${severityColor}`,
      }}
    >
      <details>
        <summary
          style={{
            cursor: "pointer",
            padding: "1rem 1.25rem",
            listStyle: "none",
            display: "flex",
            justifyContent: "space-between",
            gap: "1rem",
            alignItems: "flex-start",
          }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                display: "flex",
                gap: "0.5rem",
                alignItems: "baseline",
              }}
            >
              <span
                style={{
                  color: severityColor,
                  fontWeight: "bold",
                  fontSize: "0.95rem",
                }}
              >
                {(row.severity * 100).toFixed(0)}%
              </span>
              <span
                className="mono"
                style={{
                  fontSize: "0.6rem",
                  color: "var(--amber-dim)",
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                }}
              >
                severity
              </span>
            </div>
            <div
              style={{ marginTop: "0.3rem", fontSize: "0.85rem", lineHeight: 1.45 }}
            >
              <span style={{ color: "var(--parchment)" }}>
                &ldquo;
                {aText
                  ? aText.length > 120
                    ? aText.slice(0, 120) + "…"
                    : aText
                  : `${row.claimAId.slice(0, 8)}…`}
                &rdquo;
              </span>
              <span
                style={{
                  display: "inline-block",
                  margin: "0 0.4rem",
                  color: "var(--ember)",
                  fontSize: "0.7rem",
                }}
              >
                ↔
              </span>
              <span style={{ color: "var(--parchment)" }}>
                &ldquo;
                {bText
                  ? bText.length > 120
                    ? bText.slice(0, 120) + "…"
                    : bText
                  : `${row.claimBId.slice(0, 8)}…`}
                &rdquo;
              </span>
            </div>
          </div>
          <span
            className="mono"
            style={{
              fontSize: "0.6rem",
              color: "var(--parchment-dim)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            ▾ expand
          </span>
        </summary>
        <div
          style={{
            padding: "0 1.25rem 1rem",
            fontSize: "0.8rem",
            color: "var(--parchment-dim)",
          }}
        >
          {row.narrative && (
            <p style={{ marginBottom: "0.75rem", color: "var(--parchment)" }}>
              {row.narrative}
            </p>
          )}

          <div style={{ marginBottom: "1rem" }}>
            <div style={{ marginBottom: "0.75rem" }}>
              <div
                className="mono"
                style={{
                  fontSize: "0.6rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  color: "var(--amber-dim)",
                  marginBottom: "0.2rem",
                }}
              >
                Claim A
              </div>
              <p
                style={{
                  margin: 0,
                  color: "var(--parchment)",
                  fontSize: "0.85rem",
                  lineHeight: 1.5,
                }}
              >
                {aText || `Unresolved: ${row.claimAId}`}
              </p>
              <Link
                href={`/conclusions/${row.claimAId}`}
                style={{
                  fontSize: "0.65rem",
                  color: "var(--gold)",
                  textDecoration: "none",
                }}
              >
                View conclusion →
              </Link>
            </div>
            <div>
              <div
                className="mono"
                style={{
                  fontSize: "0.6rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  color: "var(--amber-dim)",
                  marginBottom: "0.2rem",
                }}
              >
                Claim B
              </div>
              <p
                style={{
                  margin: 0,
                  color: "var(--parchment)",
                  fontSize: "0.85rem",
                  lineHeight: 1.5,
                }}
              >
                {bText || `Unresolved: ${row.claimBId}`}
              </p>
              <Link
                href={`/conclusions/${row.claimBId}`}
                style={{
                  fontSize: "0.65rem",
                  color: "var(--gold)",
                  textDecoration: "none",
                }}
              >
                View conclusion →
              </Link>
            </div>
          </div>

          {hasRealLayerScores(row.sixLayerJson) ? (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "220px 1fr",
                gap: "1.25rem",
                alignItems: "start",
              }}
            >
              <CoherenceRadar
                values={extractLayerValues(row.sixLayerJson)}
                size={220}
              />
              <LayerBreakdown sixLayerJson={row.sixLayerJson!} />
            </div>
          ) : (
            <DetectionSummary
              source={detectionSource(row.sixLayerJson)}
              severity={row.severity}
            />
          )}

          {row.sixLayerJson && <JsonToggle json={row.sixLayerJson} />}

          <ContradictionActions
            contradictionId={row.id}
            status={row.status}
          />
        </div>
      </details>
    </li>
  );
}

function DetectionSummary({
  source,
  severity,
}: {
  source: string | null;
  severity: number;
}) {
  // Without per-layer coherence scores, the radar would render as an
  // empty rotating hex — the symptom that motivated this fallback.
  // What we DO know: which detector flagged the pair (heuristic vs.
  // LLM, possibly cross-upload), and the aggregate severity. Surface
  // that plainly so the founder can judge how much weight to give the
  // pair without staring at a meaningless visualisation.
  const sourceLabel = source
    ? source === "heuristic"
      ? "Heuristic detector"
      : source === "llm"
      ? "LLM adjudicator"
      : source.startsWith("llm")
      ? `LLM adjudicator · ${source.replace(/^llm\s*/, "")}`
      : source
    : "Unspecified";

  return (
    <div
      style={{
        padding: "0.85rem 1rem",
        border: "1px solid var(--stone-mid)",
        borderLeft: "3px solid var(--amber-dim)",
        borderRadius: 2,
        background: "rgba(212,160,23,0.03)",
        fontSize: "0.8rem",
        lineHeight: 1.55,
        color: "var(--parchment)",
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--amber-dim)",
          marginBottom: "0.4rem",
        }}
      >
        Detection summary
      </div>
      <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
        <div>
          <div
            className="mono"
            style={{
              fontSize: "0.6rem",
              color: "var(--parchment-dim)",
              textTransform: "uppercase",
            }}
          >
            Method
          </div>
          <div style={{ marginTop: "0.15rem" }}>{sourceLabel}</div>
        </div>
        <div>
          <div
            className="mono"
            style={{
              fontSize: "0.6rem",
              color: "var(--parchment-dim)",
              textTransform: "uppercase",
            }}
          >
            Severity
          </div>
          <div style={{ marginTop: "0.15rem" }}>
            {(severity * 100).toFixed(0)}%
          </div>
        </div>
      </div>
      <p
        style={{
          marginTop: "0.6rem",
          marginBottom: 0,
          fontSize: "0.72rem",
          color: "var(--parchment-dim)",
          fontStyle: "italic",
          lineHeight: 1.45,
        }}
      >
        Per-layer coherence scores aren&apos;t computed for contradictions
        yet — only aggregate severity and the narrative above. The
        six-layer radar will appear here once the pipeline produces
        per-pair layer breakdowns.
      </p>
    </div>
  );
}

function LayerBreakdown({ sixLayerJson }: { sixLayerJson: string }) {
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(sixLayerJson);
  } catch {
    return <p>No layer data available.</p>;
  }
  const layers = LAYER_KEYS.map((key) => ({
    key,
    score: typeof parsed[key] === "number" ? (parsed[key] as number) : 0,
    ...LAYER_DESCRIPTIONS[key],
  })).sort((a, b) => b.score - a.score);
  const topLayer = layers[0];

  return (
    <div>
      <div
        style={{
          marginBottom: "0.75rem",
          padding: "0.5rem 0.75rem",
          background: "rgba(180,80,40,0.08)",
          borderLeft: "3px solid var(--ember)",
          borderRadius: 2,
          fontSize: "0.8rem",
          color: "var(--parchment)",
        }}
      >
        Primary signal: <strong>{topLayer.name}</strong>{" "}
        ({(topLayer.score * 100).toFixed(0)}%) — {topLayer.explanation}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        {layers.map((layer) => {
          const hot = layer.score > 0.5;
          return (
            <div
              key={layer.key}
              title={layer.explanation}
              style={{
                display: "grid",
                gridTemplateColumns: "10rem 3rem 1fr",
                gap: "0.5rem",
                alignItems: "center",
                fontSize: "0.75rem",
              }}
            >
              <span
                className="mono"
                style={{
                  color: hot ? "var(--ember)" : "var(--parchment-dim)",
                  fontSize: "0.65rem",
                }}
              >
                {layer.name}
              </span>
              <span
                className="mono"
                style={{
                  color: hot ? "var(--ember)" : "var(--parchment-dim)",
                  textAlign: "right",
                }}
              >
                {(layer.score * 100).toFixed(0)}%
              </span>
              <div
                style={{
                  height: "4px",
                  background: "var(--stone-mid)",
                  borderRadius: 2,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${layer.score * 100}%`,
                    height: "100%",
                    background: hot ? "var(--ember)" : "var(--parchment-dim)",
                    borderRadius: 2,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
