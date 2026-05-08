import type { ReliabilityBin } from "@/lib/calibrationData";

/**
 * Server-rendered SVG calibration plot.
 *
 * Visual conventions:
 *   - X axis = predicted probability (mean of the bin).
 *   - Y axis = realized frequency (Σ outcomes / n in the bin).
 *   - Diagonal y = x is the perfectly-calibrated reference.
 *   - Vertical whiskers show the bootstrap CI on observed frequency.
 *   - Sparse bins (n < SPARSE_BIN_THRESHOLD) are drawn open (no fill,
 *     no whisker, lower opacity) and labelled "n=<count>". The page
 *     never implies more precision than the data supports.
 *   - Empty bins are not drawn.
 */
export type CalibrationPlotProps = {
  bins: ReliabilityBin[];
  width?: number;
  height?: number;
  sparseThreshold?: number;
};

export default function CalibrationPlot({
  bins,
  width = 480,
  height = 480,
  sparseThreshold = 5,
}: CalibrationPlotProps) {
  const padding = { top: 24, right: 24, bottom: 48, left: 56 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const x = (p: number) => padding.left + p * plotW;
  const y = (p: number) => padding.top + (1 - p) * plotH;

  const visibleBins = bins.filter((b) => b.n > 0 && b.meanPredicted !== null && b.observedFrequency !== null);

  const gridTicks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <figure
      role="figure"
      aria-label="Calibration plot — predicted probability vs realized frequency"
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
        {/* Diagonal reference y = x */}
        <line
          x1={x(0)}
          y1={y(0)}
          x2={x(1)}
          y2={y(1)}
          stroke="#d4a017"
          strokeDasharray="4 4"
          strokeWidth={1.5}
        />
        {/* Bin whiskers (CI on observed frequency) */}
        {visibleBins.map((b, i) => {
          if (b.meanPredicted === null || b.observedFrequency === null) return null;
          if (b.sparse || b.ciLow === null || b.ciHigh === null) return null;
          return (
            <line
              key={`whisker-${i}`}
              x1={x(b.meanPredicted)}
              y1={y(b.ciLow)}
              x2={x(b.meanPredicted)}
              y2={y(b.ciHigh)}
              stroke="#3a342a"
              strokeWidth={1.5}
            />
          );
        })}
        {/* Bin points */}
        {visibleBins.map((b, i) => {
          if (b.meanPredicted === null || b.observedFrequency === null) return null;
          const sparse = b.sparse || b.n < sparseThreshold;
          const cx = x(b.meanPredicted);
          const cy = y(b.observedFrequency);
          return (
            <g key={`pt-${i}`}>
              <circle
                cx={cx}
                cy={cy}
                r={5}
                fill={sparse ? "#ffffff" : "#3a342a"}
                stroke="#3a342a"
                strokeWidth={1.5}
                opacity={sparse ? 0.85 : 1}
              />
              {sparse ? (
                <text
                  x={cx + 8}
                  y={cy - 4}
                  fontSize={10}
                  fill="#7a6d55"
                  fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
                >
                  n={b.n}
                </text>
              ) : null}
            </g>
          );
        })}
        {/* Axis labels */}
        {gridTicks.map((t) => (
          <g key={`axis-${t}`} fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace" fontSize={10} fill="#5a5247">
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
          fill="#3a342a"
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
        >
          Predicted probability
        </text>
        <text
          x={16}
          y={padding.top + plotH / 2}
          textAnchor="middle"
          fontSize={11}
          fill="#3a342a"
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          transform={`rotate(-90 16 ${padding.top + plotH / 2})`}
        >
          Realized frequency
        </text>
      </svg>
      {visibleBins.length === 0 ? (
        <figcaption
          style={{
            marginTop: "0.75rem",
            fontSize: "0.78rem",
            color: "#7a6d55",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          }}
        >
          No resolved forecasts yet — the calibration plot will populate as predictions resolve.
        </figcaption>
      ) : null}
    </figure>
  );
}
