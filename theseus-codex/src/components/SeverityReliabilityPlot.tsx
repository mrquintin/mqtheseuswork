/**
 * SeverityReliabilityPlot — calibration plot for the severity scorer.
 *
 * The severity-calibration model (noosphere.peer_review.severity_calibration)
 * fits a logistic regression predicting whether an objection, if true,
 * materially changes the conclusion. This plot is the honesty check on
 * that fit: it bins objections by predicted severity and plots the bin's
 * mean prediction against the *realized* material-change rate.
 *
 * Visual conventions (mirrors CalibrationPlot.tsx):
 *   - X axis = predicted severity (mean of the bin).
 *   - Y axis = realized material-change rate (Σ material outcomes / n).
 *   - The dashed gold diagonal y = x is the perfect-calibration line:
 *     a point above it means the model under-called severity in that
 *     bin; below, it over-called.
 *   - Every drawn bin is labelled with its sample size n.
 *   - Sparse bins (n < sparseThreshold) are greyed: hollow marker, lower
 *     opacity. A thin bin must never look like a confident point.
 *   - Empty bins are not drawn.
 *
 * Server-rendered, no client JS. The SVG scales via viewBox + width:100%.
 */

export type SeverityReliabilityBin = {
  lo: number;
  hi: number;
  n: number;
  meanPredicted: number | null;
  realizedChangeRate: number | null;
  sparse: boolean;
};

export type SeverityReliabilityPlotProps = {
  bins: SeverityReliabilityBin[];
  width?: number;
  height?: number;
  sparseThreshold?: number;
};

const DENSE_COLOR = "var(--parchment)";
const SPARSE_COLOR = "var(--parchment-dim)";
const DIAGONAL_COLOR = "var(--gold)";
const FRAME_COLOR = "rgba(255,255,255,0.12)";
const GRID_COLOR = "rgba(255,255,255,0.05)";
const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";

export default function SeverityReliabilityPlot({
  bins,
  width = 460,
  height = 460,
  sparseThreshold = 5,
}: SeverityReliabilityPlotProps) {
  const padding = { top: 22, right: 26, bottom: 46, left: 52 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const x = (p: number) => padding.left + p * plotW;
  const y = (p: number) => padding.top + (1 - p) * plotH;

  const visibleBins = bins.filter(
    (b) => b.n > 0 && b.meanPredicted !== null && b.realizedChangeRate !== null,
  );
  const isSparse = (b: SeverityReliabilityBin) =>
    b.sparse || b.n < sparseThreshold;

  const gridTicks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <figure
      role="figure"
      aria-label="Severity reliability diagram — predicted severity vs realized material-change rate"
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
          fill="rgba(0,0,0,0.18)"
          stroke={FRAME_COLOR}
        />
        {/* Grid */}
        {gridTicks.map((t) => (
          <g key={`grid-${t}`} stroke={GRID_COLOR}>
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
          x={x(0.72)}
          y={y(0.72) - 6}
          fontSize={9}
          fill={DIAGONAL_COLOR}
          fontFamily={MONO}
        >
          perfect calibration
        </text>
        {/* Bin points — every bin labelled by sample size */}
        {visibleBins.map((b, i) => {
          if (b.meanPredicted === null || b.realizedChangeRate === null) {
            return null;
          }
          const sparse = isSparse(b);
          const cx = x(b.meanPredicted);
          const cy = y(b.realizedChangeRate);
          const labelRight = b.meanPredicted <= 0.8;
          return (
            <g key={`pt-${i}`}>
              <circle
                cx={cx}
                cy={cy}
                r={5}
                fill={sparse ? "transparent" : DENSE_COLOR}
                stroke={sparse ? SPARSE_COLOR : DENSE_COLOR}
                strokeWidth={1.5}
                opacity={sparse ? 0.7 : 1}
              />
              <text
                x={labelRight ? cx + 8 : cx - 8}
                y={cy - 6}
                fontSize={10}
                fill={sparse ? SPARSE_COLOR : DENSE_COLOR}
                textAnchor={labelRight ? "start" : "end"}
                fontFamily={MONO}
              >
                n={b.n}
              </text>
            </g>
          );
        })}
        {/* Axis ticks */}
        {gridTicks.map((t) => (
          <g key={`axis-${t}`} fontFamily={MONO} fontSize={10} fill={SPARSE_COLOR}>
            <text x={x(t)} y={padding.top + plotH + 15} textAnchor="middle">
              {t.toFixed(2)}
            </text>
            <text x={padding.left - 7} y={y(t) + 3} textAnchor="end">
              {t.toFixed(2)}
            </text>
          </g>
        ))}
        <text
          x={padding.left + plotW / 2}
          y={height - 10}
          textAnchor="middle"
          fontSize={11}
          fill={DENSE_COLOR}
          fontFamily={MONO}
        >
          Predicted severity
        </text>
        <text
          x={14}
          y={padding.top + plotH / 2}
          textAnchor="middle"
          fontSize={11}
          fill={DENSE_COLOR}
          fontFamily={MONO}
          transform={`rotate(-90 14 ${padding.top + plotH / 2})`}
        >
          Realized material-change rate
        </text>
      </svg>
      <figcaption
        style={{
          marginTop: "0.55rem",
          fontSize: "0.72rem",
          color: "var(--parchment-dim)",
          lineHeight: 1.5,
          fontFamily: MONO,
        }}
      >
        {visibleBins.length === 0 ? (
          <>
            No labelled objections yet — the reliability diagram populates
            once objections have run to a resolution.
          </>
        ) : (
          <>
            <span style={{ color: DENSE_COLOR }}>● filled</span> = bin with ≥{" "}
            {sparseThreshold} objections;{" "}
            <span style={{ color: SPARSE_COLOR }}>○ grey</span> = sparse bin (n
            &lt; {sparseThreshold}). A point above the gold diagonal means the
            model under-called severity for that bin; below, it over-called.
            Every bin is labelled with its sample size.
          </>
        )}
      </figcaption>
    </figure>
  );
}
