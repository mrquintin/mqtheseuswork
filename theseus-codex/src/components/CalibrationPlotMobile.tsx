import type { ReliabilityBin } from "@/lib/calibrationData";

/**
 * Mobile reliability diagram.
 *
 * The desktop `CalibrationPlot` is a square scatter — predicted on X,
 * realized on Y, markers near a y = x diagonal. Scaled into a ~340px
 * column the markers collapse into an unreadable cluster and the
 * diagonal carries no information you can actually inspect.
 *
 * At small viewports we redraw the same data as a vertical bar chart:
 * one row per probability bin, top (0.0–0.1) to bottom (0.9–1.0). Each
 * row draws the *observed frequency* as a horizontal bar against a
 * 0..1 track, with a tick marking where a perfectly-calibrated firm
 * would land (the bin's mean predicted probability). A well-calibrated
 * bin has its bar end at the tick.
 *
 * Visual conventions match the desktop plot:
 *   - Dense bins (n ≥ sparseThreshold) draw a solid bar + bootstrap CI
 *     whisker; the tick is the perfect-calibration reference.
 *   - Sparse bins draw a hollow/grey bar, no CI — we refuse to draw an
 *     interval we cannot defend.
 *   - Every row is labelled with its sample size.
 *
 * Server-rendered, no JS: plain divs sized by percentage so the chart
 * reflows with the column and costs nothing at first paint.
 */
export type CalibrationPlotMobileProps = {
  bins: ReliabilityBin[];
  sparseThreshold?: number;
};

const DENSE_COLOR = "#3a342a";
const SPARSE_COLOR = "#a39a86";
const REFERENCE_COLOR = "#d4a017";

function pct(v: number): string {
  return `${Math.max(0, Math.min(1, v)) * 100}%`;
}

function fmtRange(lo: number, hi: number): string {
  return `${lo.toFixed(1)}–${hi.toFixed(1)}`;
}

export default function CalibrationPlotMobile({
  bins,
  sparseThreshold = 5,
}: CalibrationPlotMobileProps) {
  const visibleBins = bins
    .filter(
      (b) => b.n > 0 && b.meanPredicted !== null && b.observedFrequency !== null,
    )
    .sort((a, b) => a.lo - b.lo);
  const isSparse = (b: ReliabilityBin) => b.sparse || b.n < sparseThreshold;

  return (
    <figure
      role="figure"
      aria-label="Reliability diagram — observed frequency per predicted-probability bin, with bootstrap confidence intervals"
      data-testid="calibration-plot-mobile"
      style={{ margin: 0 }}
    >
      {visibleBins.length === 0 ? (
        <p
          style={{
            fontSize: "0.8rem",
            color: "#5a5247",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          }}
        >
          No resolved forecasts yet — the reliability diagram will populate as
          predictions resolve.
        </p>
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.55rem",
            border: "1px solid #d8d4cb",
            borderRadius: 2,
            background: "#ffffff",
            padding: "0.85rem 0.8rem",
          }}
        >
          {visibleBins.map((b) => {
            const sparse = isSparse(b);
            const observed = b.observedFrequency ?? 0;
            const predicted = b.meanPredicted ?? 0;
            const barColor = sparse ? SPARSE_COLOR : DENSE_COLOR;
            const hasCi =
              !sparse && b.ciLow !== null && b.ciHigh !== null;
            return (
              <div key={`${b.lo}-${b.hi}`} data-testid="calibration-bin-row">
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    fontFamily:
                      "ui-monospace, SFMono-Regular, Menlo, monospace",
                    fontSize: "0.72rem",
                    color: sparse ? SPARSE_COLOR : "#5a5247",
                    marginBottom: "0.2rem",
                  }}
                >
                  <span>p {fmtRange(b.lo, b.hi)}</span>
                  <span>n={b.n}</span>
                </div>
                {/* 0..1 frequency track */}
                <div
                  style={{
                    position: "relative",
                    height: 18,
                    background: "#f4f1e9",
                    border: "1px solid #e4dfd2",
                    borderRadius: 2,
                  }}
                  role="img"
                  aria-label={`Bin ${fmtRange(b.lo, b.hi)}: observed frequency ${observed.toFixed(
                    3,
                  )}, mean predicted ${predicted.toFixed(3)}, n=${b.n}${
                    sparse ? " (sparse — no confidence interval)" : ""
                  }`}
                >
                  {/* bootstrap CI band */}
                  {hasCi ? (
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        bottom: 0,
                        left: pct(b.ciLow ?? 0),
                        width: pct((b.ciHigh ?? 0) - (b.ciLow ?? 0)),
                        background: "rgba(58,52,42,0.16)",
                      }}
                    />
                  ) : null}
                  {/* observed-frequency bar */}
                  <div
                    style={{
                      position: "absolute",
                      top: 3,
                      bottom: 3,
                      left: 0,
                      width: pct(observed),
                      background: sparse ? "transparent" : barColor,
                      border: sparse ? `1px dashed ${SPARSE_COLOR}` : "none",
                      borderRadius: 1,
                    }}
                  />
                  {/* perfect-calibration reference tick (mean predicted) */}
                  <div
                    aria-hidden="true"
                    style={{
                      position: "absolute",
                      top: -2,
                      bottom: -2,
                      left: pct(predicted),
                      width: 2,
                      marginLeft: -1,
                      background: REFERENCE_COLOR,
                    }}
                  />
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontFamily:
                      "ui-monospace, SFMono-Regular, Menlo, monospace",
                    fontSize: "0.66rem",
                    color: "#7a6d55",
                    marginTop: "0.18rem",
                  }}
                >
                  <span>observed {observed.toFixed(3)}</span>
                  <span style={{ color: REFERENCE_COLOR }}>
                    predicted {predicted.toFixed(3)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <figcaption
        style={{
          marginTop: "0.6rem",
          fontSize: "0.72rem",
          color: "#5a5247",
          lineHeight: 1.5,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        }}
      >
        {visibleBins.length === 0 ? null : (
          <>
            Bar = observed frequency in the bin; the{" "}
            <span style={{ color: REFERENCE_COLOR }}>gold tick</span> marks the
            bin&rsquo;s mean predicted probability — a calibrated bin ends its
            bar at the tick. The grey band is the 90% bootstrap CI on observed
            frequency. Sparse bins (n &lt; {sparseThreshold}) are drawn hollow
            with no CI — we refuse to draw an interval we cannot defend. Every
            row is labelled with its sample size.
          </>
        )}
      </figcaption>
    </figure>
  );
}
