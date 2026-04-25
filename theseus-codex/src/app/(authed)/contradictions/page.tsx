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

/**
 * One source-context match for a claim: the upload it came from plus a
 * trimmed before/match/after triple so the UI can render the quote with
 * the claim portion highlighted. `match` is empty when the literal claim
 * text wasn't found in the upload — `before` then holds a leading
 * excerpt of the upload as best-effort context.
 */
type ClaimContext = {
  uploadId: string;
  uploadTitle: string;
  uploadCreatedAt: string;
  before: string;
  match: string;
  after: string;
};

const CONTEXT_PAD = 320; // chars of context around the matched passage
const FALLBACK_LEAD = 600; // chars of upload head when no match found

function normalizeWhitespace(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

/**
 * Find the best location of `needle` (the claim text) in `haystack`
 * (the upload's textContent). Strategy:
 *   1. Whole-needle case-insensitive substring (the common case for
 *      heuristically-extracted claims, which are copied verbatim).
 *   2. Longest 8+-word window from the needle (paraphrased LLM claims
 *      sometimes only share a contiguous run of words with the source).
 * Returns offsets into the ORIGINAL haystack (not the normalised one)
 * or null when no reasonable match exists.
 */
function locateClaim(
  haystack: string,
  needle: string,
): { start: number; end: number } | null {
  if (!haystack || !needle) return null;
  const hayLower = haystack.toLowerCase();
  const cleanNeedle = normalizeWhitespace(needle).toLowerCase();
  if (!cleanNeedle) return null;

  const direct = hayLower.indexOf(cleanNeedle);
  if (direct !== -1) {
    return { start: direct, end: direct + cleanNeedle.length };
  }

  const words = cleanNeedle.split(" ").filter((w) => w.length > 0);
  if (words.length < 8) return null;
  // Try progressively shorter windows from the middle of the claim,
  // since the start often has hedges ("I think", "it seems") and the
  // end often has qualifiers that get rewritten.
  for (let size = words.length - 1; size >= 8; size--) {
    for (let start = 0; start + size <= words.length; start++) {
      const window = words.slice(start, start + size).join(" ");
      const at = hayLower.indexOf(window);
      if (at !== -1) {
        return { start: at, end: at + window.length };
      }
    }
  }
  return null;
}

async function loadClaimContexts(
  organizationId: string,
  claimIds: string[],
  claimTexts: Record<string, string>,
): Promise<Record<string, ClaimContext[]>> {
  if (claimIds.length === 0) return {};
  const conclusions = await db.conclusion.findMany({
    where: { id: { in: claimIds }, organizationId },
    select: {
      id: true,
      sources: {
        select: {
          upload: {
            select: {
              id: true,
              title: true,
              textContent: true,
              createdAt: true,
              deletedAt: true,
            },
          },
        },
        // Two sources is plenty for context; more would just add noise
        // to the card.
        take: 2,
      },
    },
  });

  const out: Record<string, ClaimContext[]> = {};
  for (const c of conclusions) {
    const claim = claimTexts[c.id] || "";
    const ctxs: ClaimContext[] = [];
    for (const s of c.sources) {
      const u = s.upload;
      if (!u || u.deletedAt) continue;
      const text = u.textContent || "";
      if (!text) continue;
      const hit = locateClaim(text, claim);
      if (hit) {
        const beforeStart = Math.max(0, hit.start - CONTEXT_PAD);
        const afterEnd = Math.min(text.length, hit.end + CONTEXT_PAD);
        ctxs.push({
          uploadId: u.id,
          uploadTitle: u.title,
          uploadCreatedAt: u.createdAt.toISOString(),
          before:
            (beforeStart > 0 ? "…" : "") + text.slice(beforeStart, hit.start),
          match: text.slice(hit.start, hit.end),
          after:
            text.slice(hit.end, afterEnd) + (afterEnd < text.length ? "…" : ""),
        });
      } else {
        ctxs.push({
          uploadId: u.id,
          uploadTitle: u.title,
          uploadCreatedAt: u.createdAt.toISOString(),
          before:
            text.slice(0, FALLBACK_LEAD) +
            (text.length > FALLBACK_LEAD ? "…" : ""),
          match: "",
          after: "",
        });
      }
      if (ctxs.length >= 2) break; // hard cap
    }
    if (ctxs.length > 0) out[c.id] = ctxs;
  }
  return out;
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

  // For each claim, locate the surrounding passage in its source upload
  // so the card can show the quote *in context*. The bridge from claim
  // → upload runs through ConclusionSource. We compute snippets on the
  // server (textContent can be megabytes for hour-long transcripts) and
  // ship only the trimmed before/match/after triple to the client.
  const claimContexts = await loadClaimContexts(
    tenant.organizationId,
    allClaimIds,
    claimTexts,
  );

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
              claimContexts={claimContexts}
            />
          )}
          {notable.length > 0 && (
            <ContradictionBand
              label={`NOTABLE · ${notable.length}`}
              rows={notable}
              claimTexts={claimTexts}
              claimContexts={claimContexts}
            />
          )}
          {minor.length > 0 && (
            <ContradictionBand
              label={`MINOR · ${minor.length}`}
              rows={minor}
              claimTexts={claimTexts}
              claimContexts={claimContexts}
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
  claimContexts,
}: {
  label: string;
  rows: Row[];
  claimTexts: Record<string, string>;
  claimContexts: Record<string, ClaimContext[]>;
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
          <ContradictionCard
            key={c.id}
            row={c}
            claimTexts={claimTexts}
            claimContexts={claimContexts}
          />
        ))}
      </ul>
    </section>
  );
}

function ContradictionCard({
  row,
  claimTexts,
  claimContexts,
}: {
  row: Row;
  claimTexts: Record<string, string>;
  claimContexts: Record<string, ClaimContext[]>;
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
              <SourceContextPanel contexts={claimContexts[row.claimAId]} />
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
              <SourceContextPanel contexts={claimContexts[row.claimBId]} />
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

function SourceContextPanel({
  contexts,
}: {
  contexts: ClaimContext[] | undefined;
}) {
  if (!contexts || contexts.length === 0) return null;

  return (
    <details style={{ marginTop: "0.45rem" }}>
      <summary
        className="mono"
        style={{
          cursor: "pointer",
          fontSize: "0.6rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--amber-dim)",
          listStyle: "none",
        }}
      >
        ▾ Source context · {contexts.length} excerpt
        {contexts.length === 1 ? "" : "s"}
      </summary>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.6rem",
          marginTop: "0.5rem",
        }}
      >
        {contexts.map((ctx) => (
          <div
            key={ctx.uploadId}
            style={{
              padding: "0.7rem 0.85rem",
              border: "1px solid var(--stone-mid)",
              borderLeft: "2px solid var(--amber-dim)",
              borderRadius: 2,
              background: "rgba(255,255,255,0.015)",
              fontSize: "0.78rem",
              lineHeight: 1.55,
              color: "var(--parchment-dim)",
            }}
          >
            <div
              className="mono"
              style={{
                fontSize: "0.55rem",
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                color: "var(--amber-dim)",
                marginBottom: "0.4rem",
                display: "flex",
                gap: "0.7rem",
                flexWrap: "wrap",
              }}
            >
              <span style={{ color: "var(--gold)", letterSpacing: "0.16em" }}>
                {ctx.uploadTitle}
              </span>
              <span>{new Date(ctx.uploadCreatedAt).toLocaleDateString()}</span>
              {!ctx.match && <span>· No exact match — showing lede</span>}
            </div>
            <p
              style={{
                margin: 0,
                whiteSpace: "pre-wrap",
                fontFamily: "'EB Garamond', serif",
                fontSize: "0.92rem",
                color: "var(--parchment)",
              }}
            >
              {ctx.before}
              {ctx.match && (
                <mark
                  style={{
                    background: "rgba(212,160,23,0.22)",
                    color: "var(--parchment)",
                    padding: "0 0.15em",
                    borderRadius: 2,
                  }}
                >
                  {ctx.match}
                </mark>
              )}
              {ctx.after}
            </p>
          </div>
        ))}
      </div>
    </details>
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
