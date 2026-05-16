import Link from "next/link";

import CalibrationSpark from "./CalibrationSpark";
import type {
  PublicAlgorithmRow,
  PublicCalibrationPoint,
} from "@/lib/algorithmsPublicApi";
import { isOperatorEntered } from "@/lib/algorithmsPublicApi";

/**
 * Card shown on the `/algorithms` index — one per algorithm.
 *
 * The card answers, top to bottom: what is this algorithm called,
 * what does it do, what does it watch, what does it produce, what
 * principles does it rest on, how good has it been, and when did it
 * last fire. Source-principle pills link straight into the principle
 * detail pages so a curious reader can chase the lineage in one
 * click.
 */

export type AlgorithmCardProps = {
  algorithm: PublicAlgorithmRow;
  calibration?: PublicCalibrationPoint[];
};

function formatRelative(date: Date | null): string {
  if (!date) return "never";
  const ms = Date.now() - date.getTime();
  if (!Number.isFinite(ms) || ms < 0) return "just now";
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  const years = Math.floor(days / 365);
  return `${years}y ago`;
}

function hitRateLabel(hitRate: PublicAlgorithmRow["hitRate"]): string {
  if (hitRate.n === 0 || hitRate.ratio === null) return "n=0 (no resolutions)";
  return `${Math.round(hitRate.ratio * 100)}% (n=${hitRate.n})`;
}

const sectionLabelStyle: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: "0.55rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: "var(--public-muted, #888)",
  display: "block",
  marginBottom: "0.25rem",
};

export default function AlgorithmCard({ algorithm, calibration = [] }: AlgorithmCardProps) {
  return (
    <article
      data-testid="algorithm-card"
      data-algorithm-id={algorithm.id}
      className="public-card"
      style={{
        padding: "1.25rem 1.4rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.85rem",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <h2
          style={{
            margin: 0,
            fontFamily: "'EB Garamond', serif",
            fontSize: "1.35rem",
            lineHeight: 1.25,
          }}
        >
          <Link
            href={`/algorithms/${algorithm.id}`}
            style={{ color: "inherit", textDecoration: "none" }}
          >
            {algorithm.name}
          </Link>
        </h2>
        <span
          data-testid="algorithm-status"
          className="mono"
          style={{
            padding: "0.18rem 0.55rem",
            border: `1px solid ${
              algorithm.status === "ACTIVE"
                ? "var(--amber, #d4a017)"
                : algorithm.status === "PAUSED"
                  ? "var(--ember, #c0584a)"
                  : "var(--public-muted, #888)"
            }`,
            color:
              algorithm.status === "ACTIVE"
                ? "var(--amber, #d4a017)"
                : algorithm.status === "PAUSED"
                  ? "var(--ember, #c0584a)"
                  : "var(--public-muted, #888)",
            fontSize: "0.55rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
          }}
        >
          {algorithm.status.toLowerCase()}
        </span>
      </header>

      {algorithm.description ? (
        <p
          style={{
            margin: 0,
            fontFamily: "'EB Garamond', serif",
            fontSize: "1rem",
            lineHeight: 1.55,
          }}
        >
          {algorithm.description}
        </p>
      ) : null}

      <section>
        <span style={sectionLabelStyle}>inputs</span>
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.2rem",
            fontSize: "0.85rem",
          }}
        >
          {algorithm.inputs.map((inp) => (
            <li key={inp.name} style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
              <code
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: "0.75rem",
                  color: "var(--text, #eee)",
                }}
              >
                {inp.name}
              </code>
              <span style={{ color: "var(--public-muted, #888)" }}>→</span>
              <span style={{ color: "var(--public-muted, #aaa)", fontSize: "0.78rem" }}>
                {inp.observability_source || "(not wired)"}
              </span>
              {isOperatorEntered(inp) ? (
                <span
                  data-testid="operator-input-badge"
                  className="mono"
                  style={{
                    padding: "0.05rem 0.35rem",
                    border: "1px solid var(--amber, #d4a017)",
                    color: "var(--amber, #d4a017)",
                    fontSize: "0.5rem",
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                  }}
                >
                  operator input
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <span style={sectionLabelStyle}>output</span>
        <p
          style={{
            margin: 0,
            fontFamily: "'EB Garamond', serif",
            fontSize: "0.95rem",
            lineHeight: 1.5,
          }}
        >
          predicts <strong>{algorithm.output.name}</strong>
          {algorithm.output.units ? ` (${algorithm.output.units})` : ""}
          {algorithm.output.description ? ` — ${algorithm.output.description}` : ""}
        </p>
      </section>

      {algorithm.sourcePrincipleIds.length > 0 ? (
        <section>
          <span style={sectionLabelStyle}>source principles</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
            {algorithm.sourcePrincipleIds.map((pid) => (
              <Link
                key={pid}
                href={`/principles/${pid}`}
                data-testid="principle-pill"
                style={{
                  padding: "0.18rem 0.55rem",
                  border: "1px solid var(--public-muted, #888)",
                  color: "var(--public-muted, #aaa)",
                  textDecoration: "none",
                  fontSize: "0.6rem",
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                {pid.slice(0, 12)}
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <footer
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.75rem",
          flexWrap: "wrap",
          marginTop: "0.25rem",
          borderTop: "1px solid var(--border, #333)",
          paddingTop: "0.75rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span
            data-testid="hit-rate-badge"
            className="mono"
            style={{
              padding: "0.18rem 0.55rem",
              border: "1px solid rgba(160, 211, 170, 0.9)",
              color: "rgba(160, 211, 170, 0.9)",
              fontSize: "0.6rem",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
          >
            {hitRateLabel(algorithm.hitRate)}
          </span>
          <CalibrationSpark series={calibration} />
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            fontSize: "0.7rem",
            color: "var(--public-muted, #888)",
          }}
        >
          <span data-testid="last-fired">
            last fired {formatRelative(algorithm.latestInvocationAt)}
            {algorithm.latestInvocationId ? (
              <>
                {" "}·{" "}
                <Link
                  href={`/algorithms/${algorithm.id}/invocations/${algorithm.latestInvocationId}`}
                  style={{ color: "inherit", textDecoration: "underline" }}
                >
                  view latest
                </Link>
              </>
            ) : null}
          </span>
          <Link
            href={`/algorithms/${algorithm.id}`}
            style={{
              color: "var(--amber, #d4a017)",
              textDecoration: "none",
              fontSize: "0.7rem",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            view invocations →
          </Link>
        </div>
      </footer>
    </article>
  );
}
