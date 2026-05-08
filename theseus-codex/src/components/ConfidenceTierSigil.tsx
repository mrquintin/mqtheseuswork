import type { CSSProperties, ReactNode } from "react";

import {
  decimalsInDisplay,
  formatPercent,
} from "@/lib/recalibration";

/**
 * Static ASCII sigil for a conclusion's confidence tier.
 *
 * Tier taxonomy (see prisma/schema.prisma):
 *   - firm     : beliefs the firm will bet on. Sigil = solid stacked block.
 *   - founder  : single-founder conviction, not yet firm-wide. Sigil =
 *                rising tetrahedron silhouette.
 *   - open     : unresolved, under active coherence tension. Sigil =
 *                interlocking ring / spiral suggesting an unclosed loop.
 *   - retired  : formerly held, now retracted. Sigil = fractured block.
 *
 * These are small character-art compositions, not live 3D projections,
 * because they appear inline in dense lists (every conclusion card) and
 * need to be very cheap to render. The animated Platonic-solid sigils
 * from `<AsciiSigil />` are used elsewhere for page-header accents where
 * motion is affordable.
 *
 * Each sigil is 3×2 characters — compact enough to sit between a
 * metadata line and a title without dominating. Colour is pulled from
 * CSS custom properties so theme switches propagate.
 *
 * The component also optionally renders a confidence number next to the
 * sigil: when `rawConfidence` is provided, the raw is shown first, and
 * — when a recalibration result is also provided — the calibrated
 * estimate is rendered alongside it with a tooltip that links readers
 * to the public scorecard. When the recalibration sample is too small
 * for the domain, the calibrated number is hidden and a small
 * "uncalibrated — small sample" tag is rendered instead.
 *
 * The layer is one-directional in display: this component never mutates
 * `rawConfidence`; it only renders the calibrated translation alongside
 * it. The raw is the firm's stated belief.
 */

export type ConfidenceTier = "firm" | "founder" | "open" | "retired" | (string & {});

const SIGILS: Record<ConfidenceTier, { lines: string[]; colorVar: string; title: string }> = {
  firm: {
    // Solid stacked block — the firmest figure we can draw in 6 cells.
    // Reads as a weighty cornerstone.
    lines: [
      "▞█▚",
      "▚█▞",
    ],
    colorVar: "var(--amber)",
    title: "Firm — the firm commits",
  },
  founder: {
    // Rising tetrahedron silhouette. The triangle over a base suggests a
    // single founder's conviction rising above flat ground.
    lines: [
      " ◭ ",
      "═══",
    ],
    colorVar: "var(--amber)",
    title: "Founder — a single founder's conviction, not yet firm-wide",
  },
  open: {
    // Unclosed loop. `∞` with a gap — the tension isn't resolved.
    lines: [
      "╭─╮",
      "╰⋯╯",
    ],
    colorVar: "var(--amber-dim)",
    title: "Open — an unresolved coherence tension",
  },
  retired: {
    // Fractured block. The break suggests a belief that was held, then
    // broken by later evidence or revision.
    lines: [
      "▞▚▞",
      "× ×",
    ],
    colorVar: "var(--parchment-dim)",
    title: "Retired — a belief the firm formerly held",
  },
};

/** Fallback for an unrecognised tier string. Renders a quiet placeholder
 *  rather than an error so DB drift doesn't break the UI. */
const UNKNOWN = {
  lines: [" · ", " · "],
  colorVar: "var(--parchment-dim)",
  title: "Unrecognised tier",
};

/**
 * Calibration status surfaced by `recalibrate()` in `lib/recalibration.ts`.
 * Renders are split by status:
 *
 *   * `calibrated` → "calibrated estimate: X%" alongside the raw, tooltip
 *     links to the scorecard;
 *   * `insufficient_sample` / `no_model` → "uncalibrated — small sample"
 *     tag, calibrated number suppressed;
 *   * `override` → calibrated suppressed, no small-sample tag (the
 *     conclusion is intentionally opted out, not under-sampled);
 *   * `domain_missing` → render the raw alone, no badge.
 */
export type CalibrationDisplay = {
  status:
    | "calibrated"
    | "no_model"
    | "insufficient_sample"
    | "override"
    | "domain_missing";
  /** Calibrated probability in [0, 1]. Required when status === "calibrated". */
  calibrated?: number | null;
  modelId?: string | null;
  modelFitAt?: string | null;
  modelSampleSize?: number | null;
  /** Reader-facing reason. Only used to populate the override tooltip. */
  reason?: string | null;
};

export type ConfidenceTierSigilProps = {
  tier: ConfidenceTier;
  /** Font size for the sigil text. Default 0.7rem suits inline card use. */
  size?: string;
  /** Optional surrounding container style (e.g. to control margins). */
  style?: CSSProperties;
  /** Accessible title override. */
  title?: string;
  /**
   * Raw stated confidence in [0, 1]. When provided the component renders
   * a small numeric label next to the sigil. Without it, the component
   * keeps its prior pure-sigil shape.
   */
  rawConfidence?: number | null;
  /**
   * Override the formatted raw display (e.g. "70%" or "0.70"). Used to
   * cap the calibrated number's decimals so the calibrated is never
   * pseudo-precise relative to the raw.
   */
  rawDisplay?: string | null;
  /** Calibration result from `recalibrate(...)` in `@/lib/recalibration`. */
  calibration?: CalibrationDisplay | null;
  /**
   * URL of the public calibration scorecard the calibrated tooltip
   * links to. Default `/calibration`.
   */
  scorecardUrl?: string;
};

const SCORECARD_DEFAULT_URL = "/calibration";

function rawDecimals(raw: number | null | undefined, override: string | null | undefined): number {
  if (override) return decimalsInDisplay(override);
  if (raw === null || raw === undefined) return 0;
  // If the raw was passed as a probability with implied two-digit
  // percent precision (e.g. 0.7 → 70%) we default to 0 decimals on
  // the percent display.
  return 0;
}

function rawPercent(raw: number, decimals: number): string {
  return formatPercent(raw, decimals);
}

function ConfidenceLabel({
  raw,
  rawDisplay,
  calibration,
  scorecardUrl,
}: {
  raw: number;
  rawDisplay: string | null | undefined;
  calibration: CalibrationDisplay | null | undefined;
  scorecardUrl: string;
}): ReactNode {
  const decimals = rawDecimals(raw, rawDisplay);
  const rawText = rawDisplay && rawDisplay.trim() ? rawDisplay : rawPercent(raw, decimals);

  const status = calibration?.status ?? "domain_missing";
  let badge: ReactNode = null;

  if (status === "calibrated" && typeof calibration?.calibrated === "number") {
    const calibratedText = formatPercent(calibration.calibrated, decimals);
    const fitAt = calibration.modelFitAt ? new Date(calibration.modelFitAt) : null;
    const fitLabel = fitAt && !Number.isNaN(fitAt.getTime())
      ? fitAt.toISOString().slice(0, 10)
      : null;
    const sample = calibration.modelSampleSize ?? null;
    const tooltipParts = [
      "Calibrated against the firm's resolved track record.",
      fitLabel ? `Model fit: ${fitLabel}.` : null,
      sample !== null ? `Sample size: ${sample}.` : null,
      "See the public calibration scorecard.",
    ].filter(Boolean) as string[];
    badge = (
      <a
        href={scorecardUrl}
        title={tooltipParts.join(" ")}
        style={{
          color: "var(--amber)",
          textDecoration: "none",
          marginLeft: "0.45em",
          opacity: 0.92,
        }}
      >
        calibrated estimate: {calibratedText}
      </a>
    );
  } else if (status === "insufficient_sample" || status === "no_model") {
    badge = (
      <span
        title="Not enough resolved forecasts in this domain to calibrate yet."
        style={{
          color: "var(--parchment-dim)",
          marginLeft: "0.45em",
          fontStyle: "italic",
          opacity: 0.85,
        }}
      >
        uncalibrated — small sample
      </span>
    );
  } else if (status === "override") {
    badge = (
      <span
        title={calibration?.reason || "Calibration display opted out by founder."}
        style={{
          color: "var(--parchment-dim)",
          marginLeft: "0.45em",
          fontStyle: "italic",
          opacity: 0.85,
        }}
      >
        recalibration paused
      </span>
    );
  }

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        marginLeft: "0.5em",
        fontSize: "0.75rem",
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ color: "var(--parchment)" }}>{rawText}</span>
      {badge}
    </span>
  );
}

export default function ConfidenceTierSigil({
  tier,
  size = "0.7rem",
  style,
  title,
  rawConfidence,
  rawDisplay,
  calibration,
  scorecardUrl = SCORECARD_DEFAULT_URL,
}: ConfidenceTierSigilProps) {
  const spec = (SIGILS as Record<string, typeof SIGILS.firm>)[tier] ?? UNKNOWN;
  const hasNumber = typeof rawConfidence === "number" && Number.isFinite(rawConfidence);
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        ...style,
      }}
    >
      <span
        className="mono"
        role="img"
        aria-label={title ?? spec.title}
        title={title ?? spec.title}
        style={{
          display: "inline-flex",
          flexDirection: "column",
          lineHeight: 1,
          fontSize: size,
          color: spec.colorVar,
          letterSpacing: "0.05em",
          textShadow: "0 0 4px rgba(233, 163, 56, 0.25)",
        }}
      >
        {spec.lines.map((l, i) => (
          <span key={i} style={{ whiteSpace: "pre" }}>
            {l}
          </span>
        ))}
      </span>
      {hasNumber ? (
        <ConfidenceLabel
          raw={rawConfidence as number}
          rawDisplay={rawDisplay}
          calibration={calibration}
          scorecardUrl={scorecardUrl}
        />
      ) : null}
    </span>
  );
}
