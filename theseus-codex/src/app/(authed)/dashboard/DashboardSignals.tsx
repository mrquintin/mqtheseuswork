import Link from "next/link";

/**
 * Operational signal strip rendered under the dashboard review summary.
 *
 * Folds the previously-stacked "X failed uploads", "Y unseen responses",
 * "Z active contradictions", "N decay events", and pending-deletion
 * cards into a single compact row. Each indicator is a quiet pill that
 * deep-links to the relevant queue. Items with zero counts are omitted;
 * if everything is zero the strip renders a small "all clear" line so
 * the operator still sees that the panel is working.
 *
 * Severity vocabulary:
 *   - "danger"  → red ember (failed uploads, expired conclusions, contradictions)
 *   - "warning" → amber (decaying conclusions, deletion requests, unseen responses)
 *   - "info"    → neutral (in-progress uploads)
 */

export type DashboardSignalTone = "info" | "warning" | "danger";

export type DashboardSignal = {
  key: string;
  tone: DashboardSignalTone;
  label: string;
  count: number;
  detail?: string;
  href: string;
};

const TONE_BORDER: Record<DashboardSignalTone, string> = {
  info: "var(--border)",
  warning: "var(--amber-dim)",
  danger: "var(--ember)",
};

const TONE_TEXT: Record<DashboardSignalTone, string> = {
  info: "var(--parchment)",
  warning: "var(--amber)",
  danger: "var(--ember)",
};

export default function DashboardSignals({
  signals,
}: {
  signals: DashboardSignal[];
}) {
  const visible = signals.filter((s) => s.count > 0);

  return (
    <section
      aria-label="Operational signals"
      data-testid="dashboard-signals"
      style={{
        border: "1px solid var(--border)",
        borderRadius: 3,
        padding: "0.6rem 0.85rem",
        marginBottom: "1.25rem",
        background: "rgba(0, 0, 0, 0.18)",
      }}
    >
      <div
        className="mono"
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.58rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          marginBottom: visible.length > 0 ? "0.45rem" : 0,
        }}
      >
        Signals
      </div>
      {visible.length === 0 ? (
        <p
          style={{
            margin: 0,
            color: "var(--parchment-dim)",
            fontSize: "0.82rem",
          }}
        >
          No failures, contradictions, or pending requests.
        </p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexWrap: "wrap",
            gap: "0.45rem",
          }}
        >
          {visible.map((signal) => (
            <li key={signal.key} style={{ margin: 0 }}>
              <Link
                href={signal.href}
                data-testid={`dashboard-signal-${signal.key}`}
                style={{
                  display: "inline-flex",
                  alignItems: "baseline",
                  gap: "0.45rem",
                  padding: "0.32rem 0.6rem",
                  border: `1px solid ${TONE_BORDER[signal.tone]}`,
                  borderRadius: 2,
                  textDecoration: "none",
                  color: TONE_TEXT[signal.tone],
                  fontSize: "0.78rem",
                  background: "rgba(10, 10, 10, 0.28)",
                }}
              >
                <span
                  className="mono"
                  style={{ fontSize: "0.78rem", fontWeight: 600 }}
                >
                  {signal.count}
                </span>
                <span>{signal.label}</span>
                {signal.detail ? (
                  <span
                    className="mono"
                    style={{
                      fontSize: "0.6rem",
                      color: "var(--parchment-dim)",
                      letterSpacing: "0.1em",
                    }}
                  >
                    {signal.detail}
                  </span>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
