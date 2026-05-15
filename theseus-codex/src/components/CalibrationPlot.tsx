import type { ReliabilityBin } from "@/lib/calibrationData";

/**
 * Server-rendered SVG reliability diagram.
 *
 * Visual conventions:
 *   - X axis = predicted probability (mean of the bin).
 *   - Y axis = realized frequency (Σ outcomes / n in the bin).
 *   - The dashed gold diagonal y = x is the perfect-calibration reference.
 *   - Vertical whiskers show the *bootstrap* CI on observed frequency
 *     (the manifest's `ci_low`/`ci_high` — a non-parametric percentile
 *     bootstrap, never an analytic normal approximation).
 *   - Every drawn bin is labelled with its sample size `n=<count>`.
 *   - Sparse bins (n < sparseThreshold) are greyed: hollow grey marker,
 *     no whisker, lower opacity. A thin bin must never look like a
 *     confident point.
 *   - Empty bins are not drawn.
 *
 * Mobile: the SVG scales via `viewBox` + `width: 100%`, and the figure
 * carries a text legend + caption so the diagram stays comprehensible
 * when the markers are too small to inspect individually.
 */
export type CalibrationPlotProps = {
  bins: ReliabilityBin[];
  width?: number;
  height?: number;
  sparseThreshold?: number;
};

const DENSE_COLOR = "#3a342a";
const SPARSE_COLOR = "#a39a86";
const DIAGONAL_COLOR = "#d4a017";

export default function CalibrationPlot({
  bins,
  width = 480,
  height = 480,
  sparseThreshold = 5,
}: CalibrationPlotProps) {
  const padding = { top: 24, right: 28, bottom: 48, left: 56 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const x = (p: number) => padding.left + p * plotW;
  const y = (p: number) => padding.top + (1 - p) * plotH;

  const visibleBins = bins.filter(
    (b) => b.n > 0 && b.meanPredicted !== null && b.observedFrequency !== null,
  );
  const isSparse = (b: ReliabilityBin) => b.sparse || b.n < sparseThreshold;

  const gridTicks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <figure
      role="figure"
      aria-label="Reliability diagram — predicted probability vs realized frequency, with bootstrap confidence intervals per bin"
      style={{ margin: 0 }}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-hidden="false"
        xmlns="http://www.w3.org/2000/svg"
        style={{ width: "100%", height: "auto", maxWidth: width }}
      >
        <rect
          x={padding.left}
          y={padding.top}
          width={plotW}
          height={plotH}
          fill="#ffffff"
          stroke="#d8d4cb"
        />
        {/* Grid */}
        {gridTicks.map((t) => (
          <g key={`grid-${t}`} stroke="#ece8de" strokeDasharray="2 3">
            <line x1={x(t)} y1={padding.top} x2={x(t)} y2={padding.top + plotH} />
            <line x1={padding.left} y1={y(t)} x2={padding.left + plotW} y2={y(t)} />
          </g>
        ))}
        {/* Diagonal reference y = x — perfect calibration */}
        <line
          x1={x(0)}
          y1={y(0)}
          x2={x(1)}
          y2={y(1)}
          stroke={DIAGONAL_COLOR}
          strokeDasharray="4 4"
          strokeWidth={1.5}
        />
        <text
          x={x(0.78)}
          y={y(0.78) - 6}
          fontSize={9}
          fill={DIAGONAL_COLOR}
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
        >
          perfect calibration
        </text>
        {/* Bin whiskers — bootstrap CI on observed frequency */}
        {visibleBins.map((b, i) => {
          if (b.meanPredicted === null || b.observedFrequency === null) return null;
          if (isSparse(b) || b.ciLow === null || b.ciHigh === null) return null;
          return (
            <g key={`whisker-${i}`} stroke={DENSE_COLOR} strokeWidth={1.5}>
              <line
                x1={x(b.meanPredicted)}
                y1={y(b.ciLow)}
                x2={x(b.meanPredicted)}
                y2={y(b.ciHigh)}
              />
              <line
                x1={x(b.meanPredicted) - 3}
                y1={y(b.ciLow)}
                x2={x(b.meanPredicted) + 3}
                y2={y(b.ciLow)}
              />
              <line
                x1={x(b.meanPredicted) - 3}
                y1={y(b.ciHigh)}
                x2={x(b.meanPredicted) + 3}
                y2={y(b.ciHigh)}
              />
            </g>
          );
        })}
        {/* Bin points — every bin labelled by sample size */}
        {visibleBins.map((b, i) => {
          if (b.meanPredicted === null || b.observedFrequency === null) return null;
          const sparse = isSparse(b);
          const cx = x(b.meanPredicted);
          const cy = y(b.observedFrequency);
          // Keep the n= label inside the frame on the far-right bins.
          const labelRight = b.meanPredicted <= 0.8;
          return (
            <g key={`pt-${i}`}>
              <circle
                cx={cx}
                cy={cy}
                r={5}
                fill={sparse ? "#ffffff" : DENSE_COLOR}
                stroke={sparse ? SPARSE_COLOR : DENSE_COLOR}
                strokeWidth={1.5}
                opacity={sparse ? 0.7 : 1}
              />
              <text
                x={labelRight ? cx + 8 : cx - 8}
                y={cy - 6}
                fontSize={10}
                fill={sparse ? SPARSE_COLOR : "#5a5247"}
                textAnchor={labelRight ? "start" : "end"}
                fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
              >
                n={b.n}
              </text>
            </g>
          );
        })}
        {/* Axis labels */}
        {gridTicks.map((t) => (
          <g
            key={`axis-${t}`}
            fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
            fontSize={10}
            fill="#5a5247"
          >
            <text x={x(t)} y={padding.top + plotH + 16} textAnchor="middle">
              {t.toFixed(2)}
            </text>
            <text x={padding.left - 8} y={y(t) + 3} textAnchor="end">
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        <text
          x={padding.left + plotW / 2}
          y={height - 12}
          textAnchor="middle"
          fontSize={11}
          fill={DENSE_COLOR}
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
        >
          Predicted probability
        </text>
        <text
          x={16}
          y={padding.top + plotH / 2}
          textAnchor="middle"
          fontSize={11}
          fill={DENSE_COLOR}
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          transform={`rotate(-90 16 ${padding.top + plotH / 2})`}
        >
          Realized frequency
        </text>
      </svg>
      <figcaption
        style={{
          marginTop: "0.6rem",
          fontSize: "0.74rem",
          color: "#5a5247",
          lineHeight: 1.5,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        }}
      >
        {visibleBins.length === 0 ? (
          <>
            No resolved forecasts yet — the reliability diagram will populate as
            predictions resolve.
          </>
        ) : (
          <>
            <span style={{ color: DENSE_COLOR }}>● filled</span> = bin with ≥{" "}
            {sparseThreshold} resolutions; whisker = 90% bootstrap CI on observed
            frequency.{" "}
            <span style={{ color: SPARSE_COLOR }}>○ grey</span> = sparse bin (n &lt;{" "}
            {sparseThreshold}), no CI drawn — we refuse to draw an interval we
            cannot defend. Every bin is labelled with its sample size.
          </>
        )}
      </figcaption>
    </figure>
  );
}
