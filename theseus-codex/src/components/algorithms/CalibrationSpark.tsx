import type { CSSProperties } from "react";

import type { PublicCalibrationPoint } from "@/lib/algorithmsPublicApi";

/**
 * Tiny SVG sparkline of cumulative correctness over invocation index.
 *
 * Used inline on the index card and inline on the detail page. The
 * series the loader produces is already cumulative (0..1) so the
 * renderer just needs to scale x by index and y by ratio.
 *
 * A flat series with fewer than two points renders as a horizontal
 * dash so the card still occupies the same vertical space — the
 * surface loses information when cards jump in height.
 */

export type CalibrationSparkProps = {
  series: PublicCalibrationPoint[];
  width?: number;
  height?: number;
  strokeColor?: string;
  fillColor?: string;
  ariaLabel?: string;
};

export default function CalibrationSpark({
  series,
  width = 96,
  height = 24,
  strokeColor = "var(--amber, #d4a017)",
  fillColor = "color-mix(in srgb, var(--amber, #d4a017) 12%, transparent)",
  ariaLabel,
}: CalibrationSparkProps) {
  const pad = 2;
  const innerWidth = Math.max(1, width - pad * 2);
  const innerHeight = Math.max(1, height - pad * 2);

  const wrapStyle: CSSProperties = {
    display: "inline-block",
    lineHeight: 0,
  };

  if (!series || series.length === 0) {
    return (
      <span
        data-testid="calibration-spark-empty"
        style={{
          display: "inline-block",
          width,
          height,
          color: "var(--public-muted, #888)",
          fontSize: "0.6rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          textAlign: "center",
          lineHeight: `${height}px`,
        }}
        aria-label={ariaLabel ?? "no calibration data yet"}
      >
        no data
      </span>
    );
  }

  if (series.length === 1) {
    const ratio = series[0].ratio;
    const y = pad + (1 - ratio) * innerHeight;
    return (
      <svg
        role="img"
        aria-label={ariaLabel ?? `calibration ratio ${ratio.toFixed(2)}`}
        width={width}
        height={height}
        style={wrapStyle}
      >
        <line
          x1={pad}
          x2={width - pad}
          y1={y}
          y2={y}
          stroke={strokeColor}
          strokeWidth={1.5}
        />
      </svg>
    );
  }

  const denom = series.length - 1;
  const points = series.map((point, idx) => {
    const x = pad + (idx / denom) * innerWidth;
    const y = pad + (1 - point.ratio) * innerHeight;
    return [x, y] as const;
  });
  const path = points
    .map(([x, y], idx) => `${idx === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`)
    .join(" ");
  const fillPath = `${path} L${(width - pad).toFixed(2)},${(height - pad).toFixed(2)} L${pad.toFixed(2)},${(height - pad).toFixed(2)} Z`;

  const last = series[series.length - 1];
  return (
    <svg
      role="img"
      aria-label={
        ariaLabel ?? `calibration ${last.ratio.toFixed(2)} after ${series.length} resolutions`
      }
      width={width}
      height={height}
      style={wrapStyle}
      data-testid="calibration-spark"
    >
      <path d={fillPath} fill={fillColor} stroke="none" />
      <path d={path} fill="none" stroke={strokeColor} strokeWidth={1.4} />
    </svg>
  );
}
