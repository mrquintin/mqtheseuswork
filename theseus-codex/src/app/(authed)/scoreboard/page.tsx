import { Prisma } from "@prisma/client";
import Link from "next/link";
import { db } from "@/lib/db";

type PredRow = { id: string; author_key: string; status: string; payload_json: string };
type ResRow = { predictive_claim_id: string; payload_json: string };
type ConRow = { payload_json: string };

function safeJson<T>(s: string): T | null {
  try {
    return JSON.parse(s) as T;
  } catch {
    return null;
  }
}

function clamp01(x: number) {
  return Math.min(1, Math.max(0, x));
}

function brier(p: number, y: number) {
  return (p - y) * (p - y);
}

function logloss(p: number, y: number) {
  const pe = Math.min(1 - 1e-6, Math.max(1e-6, p));
  return y === 1 ? -Math.log(pe) : -Math.log(1 - pe);
}

export default async function ScoreboardPage({
  searchParams,
}: {
  searchParams: Promise<{ author?: string; engage?: string }>;
}) {
  const sp = await searchParams;
  const filterAuthor = sp.author?.trim() || "";
  const engage = sp.engage === "1";

  let preds: PredRow[] = [];
  let ress: ResRow[] = [];
  let cons: ConRow[] = [];
  try {
    preds = await db.$queryRaw<PredRow[]>(Prisma.sql`
      SELECT id, author_key, status, payload_json FROM predictive_claim
      ORDER BY datetime(created_at) DESC LIMIT 500
    `);
  } catch {
    preds = [];
  }
  try {
    ress = await db.$queryRaw<ResRow[]>(Prisma.sql`
      SELECT predictive_claim_id, payload_json FROM prediction_resolution
    `);
  } catch {
    ress = [];
  }
  try {
    cons = await db.$queryRaw<ConRow[]>(Prisma.sql`
      SELECT payload_json FROM conclusion ORDER BY rowid DESC LIMIT 60
    `);
  } catch {
    cons = [];
  }

  const resByPred = new Map<string, { outcome: number }>();
  for (const r of ress) {
    const j = safeJson<{ outcome?: number }>(r.payload_json);
    if (j && (j.outcome === 0 || j.outcome === 1)) {
      resByPred.set(r.predictive_claim_id, { outcome: j.outcome });
    }
  }

  type Scored = { p: number; y: number; author: string; domain: string };
  const scored: Scored[] = [];
  for (const row of preds) {
    const j = safeJson<{
      status?: string;
      scoring_eligible?: boolean;
      honest_uncertainty?: boolean;
      prob_low?: number;
      prob_high?: number;
      domains?: string[];
      author_key?: string;
    }>(row.payload_json);
    if (!j) continue;
    const st = j.status || row.status;
    if (st !== "resolved") continue;
    if (j.honest_uncertainty || j.scoring_eligible === false) continue;
    const res = resByPred.get(row.id);
    if (!res) continue;
    const lo = Number(j.prob_low ?? 0.5);
    const hi = Number(j.prob_high ?? 0.5);
    const p = clamp01((lo + hi) / 2);
    const dom =
      Array.isArray(j.domains) && j.domains.length ? j.domains[0] : "unspecified";
    const author = j.author_key || row.author_key || "unknown";
    scored.push({ p, y: res.outcome, author, domain: dom });
  }

  const byAuthor = new Map<string, Scored[]>();
  for (const s of scored) {
    const arr = byAuthor.get(s.author) ?? [];
    arr.push(s);
    byAuthor.set(s.author, arr);
  }

  const authorSummaries = [...byAuthor.entries()].map(([author, xs]) => {
    const n = xs.length;
    const mb = xs.reduce((a, x) => a + brier(x.p, x.y), 0) / n;
    const ml = xs.reduce((a, x) => a + logloss(x.p, x.y), 0) / n;
    return { author, n, meanBrier: mb, meanLogLoss: ml };
  });
  authorSummaries.sort((a, b) => a.author.localeCompare(b.author));

  const globalBins = Array.from({ length: 10 }, (_, i) => ({
    lo: i / 10,
    hi: (i + 1) / 10,
    n: 0,
    hits: 0,
  }));
  for (const s of scored) {
    const idx = Math.min(9, Math.max(0, Math.floor(s.p * 10)));
    globalBins[idx].n += 1;
    globalBins[idx].hits += s.y;
  }

  const detailRows = filterAuthor
    ? preds.filter((r) => (r.author_key || "") === filterAuthor || safeJson<{ author_key?: string }>(r.payload_json)?.author_key === filterAuthor)
    : [];

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", letterSpacing: "0.08em" }}>
        Calibration scoreboard
      </h1>
      <p style={{ color: "var(--parchment-dim)", fontSize: "0.9rem", marginBottom: "1.25rem" }}>
        Aggregate Brier and log-loss over human-confirmed, resolved predictions (honest-uncertainty bins excluded).
        This page is for accountable review, not public ranking. Per-event detail is compact unless{" "}
        <code style={{ color: "var(--gold-dim)" }}>?engage=1</code> is set for deliberate review.
      </p>

      {scored.length > 0 ? (
        <section style={{ marginBottom: "2rem" }}>
          <h2 style={{ fontSize: "0.75rem", letterSpacing: "0.15em", color: "var(--gold-dim)" }}>
            GLOBAL CALIBRATION (deciles)
          </h2>
          <p style={{ fontSize: "0.8rem", color: "var(--parchment-dim)", marginBottom: "0.5rem" }}>
            Stated probability mid (x) vs Beta(0.5,0.5) smoothed empirical resolution rate (y). Sparse bins are normal early on.
          </p>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem", color: "var(--parchment)" }}>
            <thead>
              <tr style={{ color: "var(--gold-dim)", textAlign: "left" }}>
                <th style={{ padding: "0.35rem" }}>Bin</th>
                <th style={{ padding: "0.35rem" }}>n</th>
                <th style={{ padding: "0.35rem" }}>Empirical rate</th>
              </tr>
            </thead>
            <tbody>
              {globalBins.map((b) => {
                const rate = b.n ? (b.hits + 0.5) / (b.n + 1) : NaN;
                return (
                  <tr key={b.lo} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ padding: "0.35rem" }}>
                      [{b.lo.toFixed(1)}, {b.hi.toFixed(1)})
                    </td>
                    <td style={{ padding: "0.35rem" }}>{b.n}</td>
                    <td style={{ padding: "0.35rem" }}>{b.n ? rate.toFixed(2) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ) : null}

      {authorSummaries.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)" }}>No scored predictions in the store yet.</p>
      ) : (
        <section style={{ marginBottom: "2rem" }}>
          <h2 style={{ fontSize: "0.75rem", letterSpacing: "0.15em", color: "var(--gold-dim)" }}>AUTHORS</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            {authorSummaries.map((a) => (
              <li key={a.author} className="portal-card" style={{ padding: "0.75rem 1rem" }}>
                <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: "0.5rem" }}>
                  <Link
                    href={`/scoreboard?author=${encodeURIComponent(a.author)}`}
                    style={{ color: "var(--gold)", textDecoration: "none", fontWeight: 500 }}
                  >
                    {a.author}
                  </Link>
                  <span style={{ color: "var(--parchment-dim)", fontSize: "0.8rem" }}>
                    n={a.n} · Brier {a.meanBrier.toFixed(3)} · log-loss {a.meanLogLoss.toFixed(3)}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {filterAuthor ? (
        <section>
          <h2 style={{ fontSize: "0.75rem", letterSpacing: "0.15em", color: "var(--gold-dim)" }}>
            DRILL-DOWN — {filterAuthor}
          </h2>
          <p style={{ fontSize: "0.8rem", color: "var(--parchment-dim)", marginBottom: "0.75rem" }}>
            <Link href="/scoreboard" style={{ color: "var(--gold)" }}>
              ← Back to all authors
            </Link>
          </p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {detailRows.map((row) => {
              const j = safeJson<{
                event_text?: string;
                status?: string;
                prob_low?: number;
                prob_high?: number;
                domains?: string[];
              }>(row.payload_json);
              const res = resByPred.get(row.id);
              const st = j?.status || row.status;
              const brief = engage ? j?.event_text || "—" : `${(j?.event_text || "").slice(0, 72)}${(j?.event_text || "").length > 72 ? "…" : ""}`;
              return (
                <li key={row.id} className="portal-card" style={{ padding: "0.65rem 0.9rem", fontSize: "0.85rem" }}>
                  <div style={{ color: "var(--gold-dim)", fontSize: "0.65rem" }}>
                    {st}
                    {j?.domains?.length ? ` · ${j.domains.join(", ")}` : ""}
                    {res ? ` · resolved ${res.outcome}` : ""}
                    {j?.prob_low != null && j?.prob_high != null
                      ? ` · p∈[${Number(j.prob_low).toFixed(2)},${Number(j.prob_high).toFixed(2)}]`
                      : ""}
                  </div>
                  <div style={{ color: "var(--parchment)", marginTop: "0.35rem" }}>{brief || "—"}</div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <section style={{ marginTop: "2.5rem" }}>
        <h2 style={{ fontSize: "0.75rem", letterSpacing: "0.15em", color: "var(--gold-dim)" }}>
          CONCLUSIONS — STATED VS CALIBRATION-ADJUSTED
        </h2>
        <p style={{ fontSize: "0.8rem", color: "var(--parchment-dim)", marginBottom: "0.75rem" }}>
          Rows read from the Noosphere <code style={{ color: "var(--gold-dim)" }}>conclusion</code> table in this same
          SQLite file. Enable <code style={{ color: "var(--gold-dim)" }}>THESEUS_CALIBRATION_CONFIDENCE_ENABLED</code>{" "}
          before synthesis to populate adjusted values.
        </p>
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {cons.flatMap((c, i) => {
            const j = safeJson<{
              id?: string;
              text?: string;
              confidence?: number;
              calibration_adjusted_confidence?: number;
              calibration_note?: string;
              confidence_tier?: string;
            }>(c.payload_json);
            if (!j) return [];
            const adj = j.calibration_adjusted_confidence;
            return [
              <li key={j.id || `c-${i}`} className="portal-card" style={{ padding: "0.65rem 0.9rem", fontSize: "0.82rem" }}>
                <div style={{ color: "var(--gold-dim)", fontSize: "0.65rem" }}>
                  {j.confidence_tier || "tier"} · stated {j.confidence != null ? j.confidence.toFixed(2) : "—"}
                  {adj != null ? ` · adjusted ${adj.toFixed(2)}` : ""}
                </div>
                <div style={{ color: "var(--parchment)", marginTop: "0.35rem" }}>{(j.text || "").slice(0, 220)}</div>
                {j.calibration_note ? (
                  <div style={{ color: "var(--parchment-dim)", marginTop: "0.35rem", fontSize: "0.75rem" }}>
                    {j.calibration_note}
                  </div>
                ) : null}
              </li>,
            ];
          })}
        </ul>
      </section>
    </main>
  );
}
