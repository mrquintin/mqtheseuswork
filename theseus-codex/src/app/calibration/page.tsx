import type { Metadata } from "next";
import Link from "next/link";

import CalibrationPlot from "@/components/CalibrationPlot";
import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import {
  type BrierWindow,
  type CalibrationFilter,
  type DecileEntry,
  type PublicCalibrationManifest,
  loadPublicCalibrationManifest,
} from "@/lib/calibrationData";

export const metadata: Metadata = {
  title: "Calibration Scorecard",
  description:
    "Theseus's published opinions and forecasts, scored against realized outcomes. Aggregate Brier, calibration plot, top and bottom calls, with a hash of the resolution set so the numbers can be audited.",
  openGraph: {
    title: "Theseus Calibration Scorecard",
    description:
      "How Theseus's forecasts have actually fared. Brier scores, calibration plot, best and worst calls, no cherry-picking.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";

type SearchParams = {
  domain?: string;
  method?: string;
  version?: string;
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
  };
  const manifest = await loadPublicCalibrationManifest(filter);

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-calibration-page" style={{ padding: "2rem 1.5rem" }}>
        <Hero manifest={manifest} />
        <Disclaimer manifest={manifest} />
        <Filters manifest={manifest} active={filter} />
        <PlotSection manifest={manifest} />
        <BrierWindows windows={manifest.aggregateBrier} />
        <Honesty manifest={manifest} />
        <Deciles
          best={manifest.decileBest}
          worst={manifest.decileWorst}
        />
        <Methods manifest={manifest} active={filter} />
        <ManifestPointer />
      </main>
    </>
  );
}

function Hero({ manifest }: { manifest: PublicCalibrationManifest }) {
  const overall = manifest.aggregateBrier.find((w) => w.label === "all-time");
  return (
    <section style={{ marginBottom: "2rem" }} aria-labelledby="calibration-hero-title">
      <h1 id="calibration-hero-title" className="public-title" style={{ fontSize: "2rem" }}>
        Calibration scorecard
      </h1>
      <p className="public-lede" style={{ marginTop: "0.5rem" }}>
        How Theseus's published forecasts have actually fared. Lower Brier
        is better; a well-calibrated firm tracks the dashed diagonal in
        the plot below.
      </p>
      <p
        style={{
          marginTop: "1rem",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: "0.78rem",
          color: "#5a5247",
        }}
      >
        n_resolved={manifest.counts.resolvedBinary} · all-time Brier=
        {overall?.meanBrier !== null && overall?.meanBrier !== undefined ? overall.meanBrier.toFixed(3) : "—"} · withdrawn rate=
        {manifest.withdrawnRate !== null ? `${(manifest.withdrawnRate * 100).toFixed(1)}%` : "—"}
      </p>
    </section>
  );
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
        published — not a curated subset. The SHA-256 hash below pins the
        exact resolution set used: re-derive it from the public manifest
        to verify nothing was dropped.
      </p>
      <p style={{ marginTop: "0.5rem", marginBottom: 0 }}>
        resolution_set_hash:{" "}
        <code style={{ wordBreak: "break-all" }}>{manifest.resolutionSetHash || "—"}</code>
      </p>
      <p style={{ marginTop: "0.4rem", marginBottom: 0, color: "#5a5247" }}>
        published_at: {manifest.generatedAt} · source: {manifest.source} · schema_v=
        {manifest.schemaVersion}
      </p>
      <p style={{ marginTop: "0.4rem", marginBottom: 0, color: "#5a5247" }}>
        alternative-method analysis available privately
      </p>
    </section>
  );
}

function Filters({
  manifest,
  active,
}: {
  manifest: PublicCalibrationManifest;
  active: CalibrationFilter;
}) {
  const hasFilter = Boolean(active.domain || active.methodName || active.methodVersion);
  return (
    <section style={{ marginBottom: "1.5rem" }} aria-labelledby="filters-title">
      <h2 id="filters-title" style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
        Filter
      </h2>
      <form
        method="get"
        action="/calibration"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem",
          alignItems: "flex-end",
          marginTop: "0.5rem",
        }}
      >
        <label style={{ fontSize: "0.78rem" }}>
          Domain
          <select
            name="domain"
            defaultValue={active.domain ?? ""}
            style={{ display: "block", marginTop: "0.25rem", padding: "0.35rem 0.5rem", minWidth: "12rem" }}
          >
            <option value="">All domains</option>
            {manifest.domains.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label style={{ fontSize: "0.78rem" }}>
          Method
          <select
            name="method"
            defaultValue={active.methodName ?? ""}
            style={{ display: "block", marginTop: "0.25rem", padding: "0.35rem 0.5rem", minWidth: "16rem" }}
          >
            <option value="">All methods</option>
            {manifest.methods.map((m) => (
              <option key={`${m.name}@${m.version}`} value={m.name}>
                {m.name} (n={m.n})
              </option>
            ))}
          </select>
        </label>
        <input type="hidden" name="version" value={active.methodVersion ?? ""} />
        <button
          type="submit"
          style={{
            padding: "0.45rem 1rem",
            border: "1px solid #d4a017",
            background: "#fffdf7",
            color: "#7a5b0d",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Apply
        </button>
        {hasFilter ? (
          <Link
            href="/calibration"
            style={{ fontSize: "0.78rem", color: "#5a5247", textDecoration: "underline" }}
          >
            Clear
          </Link>
        ) : null}
      </form>
    </section>
  );
}

function PlotSection({ manifest }: { manifest: PublicCalibrationManifest }) {
  return (
    <section
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.1fr)",
        gap: "1.5rem",
        marginBottom: "1.75rem",
      }}
      aria-labelledby="plot-title"
    >
      <div>
        <h2 id="plot-title" style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
          Calibration plot
        </h2>
        <CalibrationPlot
          bins={manifest.calibrationCurve}
          sparseThreshold={manifest.sparseBinThreshold || 5}
        />
      </div>
      <div>
        <h2 style={{ fontSize: "0.92rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
          Slope
        </h2>
        <p style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
          OLS slope of outcome ~ probability. A perfectly calibrated firm
          has slope ≈ 1.0; below 1 means under-discrimination, above 1
          means over-discrimination. Bootstrap CI at the published level.
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
          <p style={{ marginTop: "1rem", fontSize: "0.8rem", color: "#5a5247" }}>
            Continuous-market forecasts are scored separately as{" "}
            <code>{manifest.continuousMetricName}</code>:{" "}
            {fmt(manifest.continuousQuadraticLoss)}. Not folded into the
            binary Brier above.
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
            <div style={{ fontSize: "0.7rem", letterSpacing: "0.15em", textTransform: "uppercase", color: "#7a6d55" }}>
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
            <div style={{ fontSize: "0.72rem", color: "#7a6d55", marginTop: "0.2rem" }}>
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
          <strong>Resolved:</strong> {manifest.counts.resolvedBinary} forecasts
          (binary YES/NO) — full weight in the metrics above.
        </li>
        <li>
          <strong>Stale, unresolved:</strong> {manifest.counts.staleUnresolved}{" "}
          forecasts published more than {manifest.publishHorizonDays} days
          ago and still pending. Flagged here, not silently dropped.
        </li>
        <li>
          <strong>Withdrawn / revoked:</strong> {manifest.counts.withdrawn}{" "}
          forecasts. Excluded from calibration metrics, but counted toward
          the published withdrawn rate of{" "}
          {manifest.withdrawnRate !== null
            ? `${(manifest.withdrawnRate * 100).toFixed(1)}%`
            : "—"}
          . Pulling a bad call back is not free.
        </li>
        <li>
          <strong>Sparse bins:</strong> bins with fewer than{" "}
          {manifest.sparseBinThreshold} resolved items are drawn open with
          their <code>n</code> labelled. We refuse to draw a CI we cannot
          defend.
        </li>
      </ul>
      {manifest.notes.length > 0 ? (
        <ul
          style={{
            marginTop: "0.6rem",
            paddingLeft: "1.2rem",
            fontSize: "0.78rem",
            color: "#5a5247",
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
        <p style={{ fontSize: "0.82rem", color: "#7a6d55" }}>No entries match this filter.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {entries.map((e) => (
            <li
              key={e.predictionId}
              style={{ borderTop: "1px solid #ece8de", padding: "0.45rem 0", fontSize: "0.83rem" }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                <strong style={{ flex: 1, fontWeight: 500 }}>{e.headline || e.marketTitle}</strong>
                <span
                  style={{
                    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                    color: accent,
                  }}
                >
                  {e.brier.toFixed(3)}
                </span>
              </div>
              <div style={{ color: "#7a6d55", fontSize: "0.74rem", marginTop: "0.15rem" }}>
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
      <p style={{ fontSize: "0.82rem", color: "#5a5247", marginTop: "0.4rem" }}>
        Click a method to filter the scorecard to predictions linked through it. The
        method's full track record (calibration slope, severity gate,
        domain bounds) lives on the methodology pages.
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
              <div style={{ fontSize: "0.72rem", color: "#7a6d55", marginTop: "0.2rem" }}>
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

function ManifestPointer() {
  return (
    <section style={{ borderTop: "1px solid #ece8de", paddingTop: "1rem", color: "#5a5247", fontSize: "0.78rem" }}>
      <p style={{ margin: 0 }}>
        Auditors:{" "}
        <a
          href="/api/public/calibration/manifest"
          style={{ color: "#7a5b0d" }}
        >
          /api/public/calibration/manifest
        </a>{" "}
        returns the full data backing this page. The page renders only what the
        manifest contains; if the hash here doesn't match what you re-derive
        from the manifest's resolution set, that's a bug — please file it.
      </p>
    </section>
  );
}

function fmt(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}
