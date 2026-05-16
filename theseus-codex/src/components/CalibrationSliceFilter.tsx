import Link from "next/link";

import type { CalibrationFilter, PublicCalibrationManifest } from "@/lib/calibrationData";

/**
 * Slice surface for the calibration scorecard.
 *
 * Filter chips for domain, source method, resolution time horizon and
 * market venue. Each chip is a plain link that toggles a query param, so
 * the slice is server-rendered and shareable. The selected slice's
 * resolved sample size is always visible — a slice is only as trustworthy
 * as the n behind it, so the n is never more than a glance away.
 */

type ChipParam = "domain" | "method" | "version" | "venue" | "horizon";

function buildHref(
  active: CalibrationFilter,
  patch: Partial<Record<ChipParam, string | null>>,
): string {
  const params = new URLSearchParams();
  const current: Record<ChipParam, string | null> = {
    domain: active.domain ?? null,
    method: active.methodName ?? null,
    version: active.methodVersion ?? null,
    venue: active.venue ?? null,
    horizon: active.horizon ?? null,
  };
  const merged = { ...current, ...patch };
  (Object.keys(merged) as ChipParam[]).forEach((key) => {
    const value = merged[key];
    if (value) params.set(key, value);
  });
  const qs = params.toString();
  return qs ? `/calibration?${qs}` : "/calibration";
}

function Chip({
  href,
  label,
  active,
  count,
}: {
  href: string;
  label: string;
  active: boolean;
  count?: number;
}) {
  return (
    <Link
      href={href}
      aria-pressed={active}
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        gap: "0.35rem",
        padding: "0.28rem 0.62rem",
        border: `1px solid ${active ? "#d4a017" : "#d8d4cb"}`,
        background: active ? "#fffbeb" : "#ffffff",
        color: active ? "#7a5b0d" : "#3a342a",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: "0.74rem",
        textDecoration: "none",
        borderRadius: "999px",
        lineHeight: 1.3,
      }}
    >
      <span>{label}</span>
      {count !== undefined ? (
        <span style={{ color: "#5a4e3a" }}>n={count}</span>
      ) : null}
    </Link>
  );
}

function ChipRow({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginTop: "0.6rem" }}>
      <div
        style={{
          fontSize: "0.66rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "#5a4e3a",
          marginBottom: "0.3rem",
        }}
      >
        {title}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>{children}</div>
    </div>
  );
}

export default function CalibrationSliceFilter({
  manifest,
  active,
}: {
  manifest: PublicCalibrationManifest;
  active: CalibrationFilter;
}) {
  const hasFilter = Boolean(
    active.domain ||
      active.methodName ||
      active.methodVersion ||
      active.venue ||
      active.horizon,
  );
  const sliceN = manifest.counts.resolvedBinary;

  return (
    <section style={{ marginBottom: "1.5rem" }} aria-labelledby="slice-filter-title">
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: "0.5rem",
        }}
      >
        <h2
          id="slice-filter-title"
          style={{
            fontSize: "0.92rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            margin: 0,
          }}
        >
          Slice
        </h2>
        <p
          aria-live="polite"
          style={{
            margin: 0,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: "0.78rem",
            color: sliceN > 0 ? "#3a342a" : "#a52a2a",
          }}
        >
          {hasFilter ? "selected slice" : "all forecasts"}: n={sliceN} resolved
        </p>
      </div>

      {manifest.domains.length > 0 ? (
        <ChipRow title="Domain">
          <Chip
            href={buildHref(active, { domain: null })}
            label="All domains"
            active={!active.domain}
          />
          {manifest.domains.map((d) => (
            <Chip
              key={d}
              href={buildHref(active, { domain: active.domain === d ? null : d })}
              label={d}
              active={active.domain === d}
            />
          ))}
        </ChipRow>
      ) : null}

      {manifest.methods.length > 0 ? (
        <ChipRow title="Source method">
          <Chip
            href={buildHref(active, { method: null, version: null })}
            label="All methods"
            active={!active.methodName}
          />
          {manifest.methods.map((m) => {
            const isActive =
              active.methodName === m.name && active.methodVersion === m.version;
            return (
              <Chip
                key={`${m.name}@${m.version}`}
                href={buildHref(active, {
                  method: isActive ? null : m.name,
                  version: isActive ? null : m.version,
                })}
                label={`${m.name} v${m.version}`}
                active={isActive}
                count={m.n}
              />
            );
          })}
        </ChipRow>
      ) : null}

      {manifest.venues.length > 0 ? (
        <ChipRow title="Market venue">
          <Chip
            href={buildHref(active, { venue: null })}
            label="All venues"
            active={!active.venue}
          />
          {manifest.venues.map((v) => (
            <Chip
              key={v.key}
              href={buildHref(active, {
                venue: active.venue === v.key ? null : v.key,
              })}
              label={v.label}
              active={active.venue === v.key}
              count={v.n}
            />
          ))}
        </ChipRow>
      ) : null}

      {manifest.horizons.length > 0 ? (
        <ChipRow title="Resolution time horizon">
          <Chip
            href={buildHref(active, { horizon: null })}
            label="Any horizon"
            active={!active.horizon}
          />
          {manifest.horizons.map((h) => (
            <Chip
              key={h.key}
              href={buildHref(active, {
                horizon: active.horizon === h.key ? null : h.key,
              })}
              label={h.label}
              active={active.horizon === h.key}
              count={h.n}
            />
          ))}
        </ChipRow>
      ) : null}

      {manifest.domains.length === 0 &&
      manifest.methods.length === 0 &&
      manifest.venues.length === 0 &&
      manifest.horizons.length === 0 ? (
        <p style={{ fontSize: "0.78rem", color: "#5a4e3a", marginTop: "0.5rem" }}>
          No slices available yet — chips populate as forecasts resolve across
          domains, methods and venues.
        </p>
      ) : null}

      {hasFilter ? (
        <p style={{ marginTop: "0.6rem" }}>
          <Link
            href="/calibration"
            style={{
              fontSize: "0.76rem",
              color: "#4b4234",
              textDecoration: "underline",
            }}
          >
            Clear all slices
          </Link>
        </p>
      ) : null}
    </section>
  );
}
