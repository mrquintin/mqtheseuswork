import type { Metadata } from "next";
import Link from "next/link";

import CalibrationComparators from "@/components/CalibrationComparators";
import CalibrationPlot from "@/components/CalibrationPlot";
import CalibrationPlotMobile from "@/components/CalibrationPlotMobile";
import CalibrationSliceFilter from "@/components/CalibrationSliceFilter";
import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import {
  HEADLINE_MIN_N,
  type BrierWindow,
  type CalibrationFilter,
  type DecileEntry,
  type PublicCalibrationManifest,
  type ResolvedAuditEntry,
  loadPublicCalibrationManifest,
} from "@/lib/calibrationData";

export const metadata: Metadata = {
  title: "Calibration Scorecard",
  description:
    "Theseus's published forecasts, scored against realized outcomes. Headline Brier with bootstrap CI and sample size, a reliability diagram with per-bin CIs, comparator baselines, and a resolution audit so every number has a paper trail.",
  openGraph: {
    title: "Theseus Calibration Scorecard",
    description:
      "How Theseus's forecasts have actually fared. Headline Brier with confidence interval, comparators, full resolution audit, no cherry-picking.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

type SearchParams = {
  domain?: string;
  method?: string;
  version?: string;
  venue?: string;
  horizon?: string;
};

export default async function CalibrationPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const founder = await getFounder();
  const params = (await searchParams) ?? {};
  const filter: CalibrationFilter = {
    domain: params.domain ?? null,
    methodName: params.method ?? null,
    methodVersion: params.version ?? null,
    venue: params.venue ?? null,
    horizon: params.horizon ?? null,
  };
  const manifest = await loadPublicCalibrationManifest(filter);

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-calibration-page" style={{ padding: "2rem 1.5rem" }}>
        <Hero manifest={manifest} />
        <Disclaimer manifest={manifest} />
        <CalibrationSliceFilter manifest={manifest} active={filter} />
        <PlotSection manifest={manifest} />
        <CalibrationComparators
          headline={manifest.headlineBrier}
          outcomeBaseRate={manifest.outcomeBaseRate}
        />
        <BrierWindows windows={manifest.aggregateBrier} />
        <Honesty manifest={manifest} />
        <Deciles best={manifest.decileBest} worst={manifest.decileWorst} />
        <ResolutionAudit manifest={manifest} />
        <Methods manifest={manifest} active={filter} />
        <ManifestPointer manifest={manifest} />
      </main>
      <style>{`
        .calibration-plot-grid {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
          gap: 1.5rem;
          margin-bottom: 1.75rem;
        }
        .calibration-plot-mobile { display: none; }
        @media (max-width: 720px) {
          .calibration-plot-grid {
            grid-template-columns: minmax(0, 1fr);
            gap: 1rem;
          }
          .calibration-plot-desktop { display: none; }
          .calibration-plot-mobile { display: block; }
        }
      `}</style>
    </>
  );
}

function Hero({ manifest }: { manifest: PublicCalibrationManifest }) {
  const h = manifest.headlineBrier;
  const hasCi = h.ciLow !== null && h.ciHigh !== null;
  return (
    <section style={{ marginBottom: "2rem" }} aria-labelledby="calibration-hero-title">
      <h1 id="calibration-hero-title" className="public-title" style={{ fontSize: "2rem" }}>
        Calibration scorecard
      </h1>
      <p className="public-lede" style={{ marginTop: "0.5rem" }}>
        How Theseus's published forecasts have actually fared. Lower Brier is
        better; a well-calibrated firm tracks the dashed diagonal in the
        reliability diagram below.
      </p>
      <div
        style={{
          marginTop: "1.1rem",
          border: `1px solid ${h.stable ? "#d8d4cb" : "#d4a017"}`,
          background: h.stable ? "#fffdf7" : "#fffbeb",
          padding: "1rem 1.15rem",
        }}
        aria-labelledby="headline-brier-label"
      >
        <div
          id="headline-brier-label"
          style={{
            fontSize: "0.68rem",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "#5a4e3a",
          }}
        >
          All-time Brier score
        </div>
        {h.stable ? (
          <>
            <div
              style={{
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: "2.6rem",
                lineHeight: 1.1,
                marginTop: "0.2rem",
                color: "#3a342a",
              }}
            >
              {h.meanBrier!.toFixed(3)}
            </div>
            <div
              style={{
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: "0.8rem",
                color: "#4b4234",
                marginTop: "0.25rem",
              }}
            >
              {hasCi
                ? `${Math.round(h.ciLevel * 100)}% bootstrap CI [${h.ciLow!.toFixed(3)}, ${h.ciHigh!.toFixed(3)}]`
                : "bootstrap CI not in this manifest revision"}{" "}
              · n = {h.n} resolved forecasts
            </div>
          </>
        ) : (
          <>
            <div
              style={{
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: "1.5rem",
                lineHeight: 1.25,
                marginTop: "0.3rem",
                color: "#7a5b0d",
              }}
            >
              n = {h.n} — too few resolutions for a stable score
            </div>
            <p
              style={{
                fontSize: "0.82rem",
                color: "#4b4234",
                marginTop: "0.4rem",
                marginBottom: 0,
                lineHeight: 1.5,
              }}
            >
              A Brier over fewer than {HEADLINE_MIN_N} resolved forecasts is
              dominated by noise. We publish the count, not a flattering point
              estimate, until the resolution set is large enough to defend a
              number. The reliability diagram, comparators and audit below still
              render — they just carry the same caveat.
            </p>
          </>
        )}
      </div>
      <p
        style={{
          marginTop: "0.8rem",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: "0.76rem",
          color: "#4b4234",
        }}
      >
        n_resolved={manifest.counts.resolvedBinary} · withdrawn rate=
        {manifest.withdrawnRate !== null
          ? `${(manifest.withdrawnRate * 100).toFixed(1)}%`
          : "—"}{" "}
        · source={manifest.source} · schema_v={manifest.schemaVersion}
      </p>
    </section>
  );
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return iso;
  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function Disclaimer({ manifest }: { manifest: PublicCalibrationManifest }) {
  return (
    <section
      style={{
        border: "1px solid #d4a017",
        background: "#fffbeb",
        padding: "0.9rem 1rem",
        marginBottom: "1.5rem",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: "0.78rem",
      }}
      aria-labelledby="cherry-pick-label"
    >
      <strong id="cherry-pick-label" style={{ display: "block", marginBottom: "0.4rem" }}>
        No cherry-picking
      </strong>
      <p style={{ margin: 0 }}>
        The metrics on this page cover every resolved forecast Theseus has
        published — not a curated subset. The SHA-256 hash below pins the exact
        resolution set used: re-derive it from the public manifest to verify
        nothing was dropped.
      </p>
      <p style={{ marginTop: "0.5rem", marginBottom: 0 }}>
        resolution_set_hash:{" "}
        <code style={{ wordBreak: "break-all" }}>{manifest.resolutionSetHash || "—"}</code>
      </p>
      <p style={{ marginTop: "0.4rem", marginBottom: 0, color: "#4b4234" }}>
        pinned {formatDate(manifest.generatedAt)} ·{" "}
        <Link href="#how-to-verify" style={{ color: "#7a5b0d" }}>
          what this hash means →
        </Link>
      </p>
      <p style={{ marginTop: "0.4rem", marginBottom: 0, color: "#4b4234" }}>
        published_at: {manifest.generatedAt} · source: {manifest.source} · schema_v=
        {manifest.schemaVersion}
      </p>
      <p style={{ marginTop: "0.4rem", marginBottom: 0, color: "#4b4234" }}>
        alternative-method analysis available privately
      </p>
    </section>
  );
}

function PlotSection({ manifest }: { manifest: PublicCalibrationManifest }) {
  return (
    <section className="calibration-plot-grid" aria-labelledby="plot-title">
      <div>
        <h2 id="plot-title" style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
          Reliability diagram
        </h2>
        {/* Both renderings ship in the HTML; CSS picks one by viewport
            width, so there is no JS viewport sniffing and no layout
            shift after hydration. The scatter is unusable below ~400px,
            so the mobile build redraws it as a per-bin bar chart. */}
        <div className="calibration-plot-desktop">
          <CalibrationPlot
            bins={manifest.calibrationCurve}
            sparseThreshold={manifest.sparseBinThreshold || 5}
          />
        </div>
        <div className="calibration-plot-mobile">
          <CalibrationPlotMobile
            bins={manifest.calibrationCurve}
            sparseThreshold={manifest.sparseBinThreshold || 5}
          />
        </div>
      </div>
      <div>
        <h2 style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
          Slope
        </h2>
        <p style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
          OLS slope of outcome ~ probability. A perfectly calibrated firm has
          slope ≈ 1.0; below 1 means under-discrimination, above 1 means
          over-discrimination. Bootstrap CI at the published level.
        </p>
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            marginTop: "0.5rem",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: "0.82rem",
          }}
        >
          <li>slope = {fmt(manifest.calibrationSlope.slope)}</li>
          <li>
            ci = [{fmt(manifest.calibrationSlope.ciLow)}, {fmt(manifest.calibrationSlope.ciHigh)}]
          </li>
          <li>n = {manifest.calibrationSlope.sampleSize}</li>
        </ul>
        {manifest.continuousQuadraticLoss !== null ? (
          <p style={{ marginTop: "1rem", fontSize: "0.8rem", color: "#4b4234" }}>
            Continuous-market forecasts are scored separately as{" "}
            <code>{manifest.continuousMetricName}</code>:{" "}
            {fmt(manifest.continuousQuadraticLoss)}. Not folded into the binary
            Brier above.
          </p>
        ) : null}
      </div>
    </section>
  );
}

function BrierWindows({ windows }: { windows: BrierWindow[] }) {
  return (
    <section style={{ marginBottom: "2rem" }} aria-labelledby="windows-title">
      <h2 id="windows-title" style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
        Aggregate Brier — rolling windows
      </h2>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "0.75rem",
          marginTop: "0.5rem",
        }}
      >
        {windows.map((w) => (
          <div
            key={w.label}
            style={{
              border: "1px solid #d8d4cb",
              padding: "0.7rem 0.85rem",
              background: "#fffdf7",
            }}
          >
            <div style={{ fontSize: "0.7rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "#5a4e3a" }}>
              {w.label}
            </div>
            <div
              style={{
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: "1.05rem",
                marginTop: "0.25rem",
              }}
            >
              {fmt(w.meanBrier)}
            </div>
            <div style={{ fontSize: "0.72rem", color: "#5a4e3a", marginTop: "0.2rem" }}>
              n = {w.n} · log loss = {fmt(w.meanLogLoss)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Honesty({ manifest }: { manifest: PublicCalibrationManifest }) {
  return (
    <section style={{ marginBottom: "2rem" }} aria-labelledby="honesty-title">
      <h2 id="honesty-title" style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
        Honesty constraints
      </h2>
      <ul
        style={{
          marginTop: "0.5rem",
          paddingLeft: "1.2rem",
          fontSize: "0.83rem",
          lineHeight: 1.55,
        }}
      >
        <li>
          <strong>Headline discipline:</strong> the hero Brier is suppressed
          below {HEADLINE_MIN_N} resolved forecasts — we show the count, not a
          point estimate the sample cannot support.
        </li>
        <li>
          <strong>Resolved:</strong> {manifest.counts.resolvedBinary} forecasts
          (binary YES/NO) — full weight in the metrics above, and every one is
          listed in the resolution audit.
        </li>
        <li>
          <strong>Stale, unresolved:</strong> {manifest.counts.staleUnresolved}{" "}
          forecasts published more than {manifest.publishHorizonDays} days ago
          and still pending. Flagged here, not silently dropped.
        </li>
        <li>
          <strong>Withdrawn / revoked:</strong> {manifest.counts.withdrawn}{" "}
          forecasts. Excluded from calibration metrics, but counted toward the
          published withdrawn rate of{" "}
          {manifest.withdrawnRate !== null
            ? `${(manifest.withdrawnRate * 100).toFixed(1)}%`
            : "—"}
          . Pulling a bad call back is not free.
        </li>
        <li>
          <strong>Sparse bins:</strong> bins with fewer than{" "}
          {manifest.sparseBinThreshold} resolved items are drawn grey and open
          with their <code>n</code> labelled. We refuse to draw a CI we cannot
          defend.
        </li>
      </ul>
      {manifest.notes.length > 0 ? (
        <ul
          style={{
            marginTop: "0.6rem",
            paddingLeft: "1.2rem",
            fontSize: "0.78rem",
            color: "#4b4234",
          }}
        >
          {manifest.notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function Deciles({ best, worst }: { best: DecileEntry[]; worst: DecileEntry[] }) {
  return (
    <section style={{ marginBottom: "2rem" }} aria-labelledby="deciles-title">
      <h2 id="deciles-title" style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
        Best and worst calls
      </h2>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "1rem",
          marginTop: "0.5rem",
        }}
      >
        <DecileColumn title="Top decile (lowest Brier)" entries={best} accent="#1f6f3a" />
        <DecileColumn title="Bottom decile (highest Brier)" entries={worst} accent="#a52a2a" />
      </div>
    </section>
  );
}

function DecileColumn({
  title,
  entries,
  accent,
}: {
  title: string;
  entries: DecileEntry[];
  accent: string;
}) {
  return (
    <div>
      <h3 style={{ fontSize: "0.78rem", letterSpacing: "0.16em", textTransform: "uppercase", color: accent }}>
        {title}
      </h3>
      {entries.length === 0 ? (
        <p style={{ fontSize: "0.82rem", color: "#5a4e3a" }}>No entries match this slice.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {entries.map((e) => (
            <li
              key={e.predictionId}
              style={{ borderTop: "1px solid #ece8de", padding: "0.45rem 0", fontSize: "0.83rem" }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                <Link
                  href={`/forecasts/${encodeURIComponent(e.predictionId)}`}
                  style={{ flex: 1, fontWeight: 500, color: "#3a342a" }}
                >
                  {e.headline || e.marketTitle}
                </Link>
                <span
                  style={{
                    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                    color: accent,
                  }}
                >
                  {e.brier.toFixed(3)}
                </span>
              </div>
              <div style={{ color: "#5a4e3a", fontSize: "0.74rem", marginTop: "0.15rem" }}>
                p={e.probabilityYes.toFixed(3)} · resolved {e.outcome}
                {e.methodName ? (
                  <>
                    {" · "}
                    <Link
                      href={`/calibration?method=${encodeURIComponent(e.methodName)}${e.methodVersion ? `&version=${encodeURIComponent(e.methodVersion)}` : ""}`}
                      style={{ color: "#7a5b0d" }}
                    >
                      {e.methodName}
                    </Link>
                  </>
                ) : null}
                {" · "}
                <Link
                  href={`/forecasts/${encodeURIComponent(e.predictionId)}`}
                  style={{ color: "#7a5b0d" }}
                >
                  record →
                </Link>
                {e.marketUrl ? (
                  <>
                    {" · "}
                    <a href={e.marketUrl} rel="noreferrer" style={{ color: "#7a5b0d" }}>
                      market →
                    </a>
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ResolutionAudit({ manifest }: { manifest: PublicCalibrationManifest }) {
  const entries: ResolvedAuditEntry[] = manifest.resolvedIndex;
  return (
    <section
      id="resolution-audit"
      style={{ marginBottom: "2rem" }}
      aria-labelledby="resolution-audit-title"
    >
      <h2
        id="resolution-audit-title"
        style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}
      >
        Resolution audit
      </h2>
      <p style={{ fontSize: "0.83rem", marginTop: "0.4rem", lineHeight: 1.55 }}>
        Every resolved forecast in the numerator above, one click from its
        underlying record. This is what makes the scorecard non-fakeable: the
        headline Brier is just the mean of these {entries.length} squared
        errors, and each is independently checkable.
      </p>
      {!manifest.resolvedIndexComplete && entries.length > 0 ? (
        <p
          style={{
            fontSize: "0.76rem",
            color: "#7a5b0d",
            background: "#fffbeb",
            border: "1px solid #d4a017",
            padding: "0.5rem 0.7rem",
            margin: "0.5rem 0",
          }}
        >
          Partial index: this manifest revision publishes only the best/worst
          decile entries, not the full per-forecast index. The complete audit
          appears once the nightly scheduler emits a manifest with{" "}
          <code>resolution_index</code>.
        </p>
      ) : null}
      {entries.length === 0 ? (
        <p style={{ fontSize: "0.82rem", color: "#5a4e3a" }}>
          No resolved forecasts yet — the audit list populates as predictions
          resolve.
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "0.78rem",
              marginTop: "0.5rem",
            }}
          >
            <thead>
              <tr style={{ textAlign: "left", color: "#5a4e3a" }}>
                <th style={{ padding: "0.35rem 0.5rem 0.35rem 0" }}>Forecast</th>
                <th style={{ padding: "0.35rem 0.5rem" }}>p(YES)</th>
                <th style={{ padding: "0.35rem 0.5rem" }}>Outcome</th>
                <th style={{ padding: "0.35rem 0.5rem" }}>Brier</th>
                <th style={{ padding: "0.35rem 0.5rem" }}>Venue</th>
                <th style={{ padding: "0.35rem 0.5rem" }}>Record</th>
              </tr>
            </thead>
            <tbody style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
              {entries.map((e) => (
                <tr key={e.predictionId} style={{ borderTop: "1px solid #ece8de" }}>
                  <td
                    style={{
                      padding: "0.4rem 0.5rem 0.4rem 0",
                      fontFamily: "inherit",
                      maxWidth: "22rem",
                    }}
                  >
                    <Link
                      href={`/forecasts/${encodeURIComponent(e.predictionId)}`}
                      style={{ color: "#3a342a" }}
                    >
                      {e.headline || e.marketTitle || e.predictionId}
                    </Link>
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    {e.probabilityYes.toFixed(3)}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{e.outcome}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{e.brier.toFixed(3)}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{e.venue ?? "—"}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    <Link
                      href={`/forecasts/${encodeURIComponent(e.predictionId)}`}
                      style={{ color: "#7a5b0d" }}
                    >
                      open →
                    </Link>
                    {e.marketUrl ? (
                      <>
                        {" "}
                        <a
                          href={e.marketUrl}
                          rel="noreferrer"
                          style={{ color: "#7a5b0d" }}
                        >
                          market →
                        </a>
                      </>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Methods({
  manifest,
  active,
}: {
  manifest: PublicCalibrationManifest;
  active: CalibrationFilter;
}) {
  if (manifest.methods.length === 0) return null;
  return (
    <section style={{ marginBottom: "2rem" }} aria-labelledby="methods-title">
      <h2 id="methods-title" style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
        Per-method drill-down
      </h2>
      <p style={{ fontSize: "0.82rem", color: "#4b4234", marginTop: "0.4rem" }}>
        Click a method to slice the scorecard to predictions linked through it. The
        method's full track record (calibration slope, severity gate, domain
        bounds) lives on the methodology pages.
      </p>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          marginTop: "0.5rem",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "0.5rem",
        }}
      >
        {manifest.methods.map((m) => {
          const isActive = active.methodName === m.name;
          const href = isActive
            ? "/calibration"
            : `/calibration?method=${encodeURIComponent(m.name)}&version=${encodeURIComponent(m.version)}`;
          return (
            <li
              key={`${m.name}@${m.version}`}
              style={{
                border: `1px solid ${isActive ? "#d4a017" : "#d8d4cb"}`,
                background: isActive ? "#fffbeb" : "#ffffff",
                padding: "0.6rem 0.8rem",
              }}
            >
              <Link
                href={href}
                style={{
                  textDecoration: "none",
                  color: "#3a342a",
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                  fontSize: "0.85rem",
                }}
              >
                {m.name}
              </Link>
              <div style={{ fontSize: "0.72rem", color: "#5a4e3a", marginTop: "0.2rem" }}>
                v{m.version} · n={m.n} ·{" "}
                <Link
                  href={`/methodology/${encodeURIComponent(m.name)}/track-record`}
                  style={{ color: "#7a5b0d" }}
                >
                  full record →
                </Link>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ManifestPointer({ manifest }: { manifest: PublicCalibrationManifest }) {
  return (
    <section
      id="how-to-verify"
      style={{ borderTop: "1px solid #ece8de", paddingTop: "1rem", color: "#4b4234", fontSize: "0.78rem" }}
    >
      <h2
        style={{
          fontSize: "0.82rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "#4b4234",
        }}
      >
        How to verify this hash
      </h2>
      <p style={{ marginTop: "0.4rem" }}>
        The <code>resolution_set_hash</code> is a SHA-256 over the canonicalized
        set of resolved forecasts — every <code>(prediction_id, probability,
        outcome, resolved_at, brier)</code> tuple, sorted and rounded to a fixed
        precision. It pins exactly which forecasts the headline Brier averages
        over. If the firm quietly dropped a bad call, the hash would change.
      </p>
      <p style={{ marginTop: "0.5rem" }}>
        Auditors:{" "}
        <a href="/api/public/calibration/manifest" style={{ color: "#7a5b0d" }}>
          /api/public/calibration/manifest
        </a>{" "}
        returns the full data backing this page, including the resolution index.
        Re-derive the hash from the manifest's resolution set and compare: it
        must match the value above ({manifest.resolutionSetHash ? (
          <code style={{ wordBreak: "break-all" }}>{manifest.resolutionSetHash}</code>
        ) : (
          "—"
        )}
        ). A mismatch is a bug — please file it.
      </p>
    </section>
  );
}

function fmt(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}
