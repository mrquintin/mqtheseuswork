import Link from "next/link";

/**
 * Operator-only calibration triage queue panel.
 *
 * The Python calibration tick (prompt 05) lays down PENDING rows
 * here when a retirement / promotion trigger fires. The founder
 * accepts, rejects, or defers; the agent never auto-retires.
 */

export type TriageAction = "NONE" | "RETIRE" | "PROMOTE";
export type TriageStatus =
  | "PENDING"
  | "ACCEPTED"
  | "REJECTED"
  | "DEFERRED";

export type CalibrationTriageRow = {
  id: string;
  algorithmId: string;
  algorithmName: string;
  recommendedAt: Date;
  recommendedAction: TriageAction;
  triggerReasons: string[];
  recommendedMultiplier: number;
  narrative: string;
};

type Props = {
  rows: CalibrationTriageRow[];
  acceptAction: (formData: FormData) => Promise<void>;
  rejectAction: (formData: FormData) => Promise<void>;
  deferAction: (formData: FormData) => Promise<void>;
};

export default function CalibrationTriagePanel({
  rows,
  acceptAction,
  rejectAction,
  deferAction,
}: Props) {
  return (
    <section
      className="public-section"
      data-testid="calibration-triage-panel"
    >
      <h2>Calibration triage queue · {rows.length}</h2>
      {rows.length === 0 ? (
        <p style={{ color: "var(--public-muted, #888)" }}>
          No pending calibration recommendations. The agent will surface
          retirement or promotion candidates here once enough resolutions
          have landed.
        </p>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.85rem",
          }}
        >
          {rows.map((row) => (
            <li
              key={row.id}
              data-testid="calibration-triage-row"
              data-recommendation-id={row.id}
              data-recommended-action={row.recommendedAction}
              style={{
                padding: "0.85rem 1rem",
                border: "1px solid var(--border, #333)",
                borderRadius: 3,
                background: "var(--stone-light, #1d1d1d)",
                display: "flex",
                flexDirection: "column",
                gap: "0.55rem",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "0.85rem",
                  alignItems: "baseline",
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <Link
                    href={`/algorithms/${row.algorithmId}`}
                    style={{
                      color: "var(--text, #eee)",
                      textDecoration: "none",
                    }}
                  >
                    <strong>{row.algorithmName}</strong>
                  </Link>
                  <span
                    style={{
                      marginLeft: "0.6rem",
                      fontSize: "0.7rem",
                      letterSpacing: "0.18em",
                      textTransform: "uppercase",
                      color:
                        row.recommendedAction === "RETIRE"
                          ? "var(--ember, #c0584a)"
                          : "var(--amber, #d4a017)",
                    }}
                  >
                    recommend {row.recommendedAction.toLowerCase()}
                    {row.recommendedAction === "PROMOTE"
                      ? ` → weight ${row.recommendedMultiplier.toFixed(2)}`
                      : ""}
                  </span>
                </div>
                <span
                  style={{
                    color: "var(--public-muted, #888)",
                    fontSize: "0.7rem",
                  }}
                >
                  {row.recommendedAt.toISOString().slice(0, 10)}
                </span>
              </div>
              {row.narrative ? (
                <p
                  style={{
                    margin: 0,
                    fontFamily: "'EB Garamond', serif",
                    fontSize: "0.95rem",
                    color: "var(--public-muted, #ccc)",
                  }}
                >
                  {row.narrative}
                </p>
              ) : null}
              {row.triggerReasons.length > 0 ? (
                <ul
                  data-testid="trigger-reasons"
                  style={{
                    listStyle: "none",
                    margin: 0,
                    padding: 0,
                    display: "flex",
                    gap: "0.4rem",
                    flexWrap: "wrap",
                  }}
                >
                  {row.triggerReasons.map((reason) => (
                    <li
                      key={reason}
                      style={{
                        padding: "0.18rem 0.5rem",
                        border: "1px solid var(--public-muted, #555)",
                        color: "var(--public-muted, #aaa)",
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: "0.65rem",
                        letterSpacing: "0.08em",
                      }}
                    >
                      {reason}
                    </li>
                  ))}
                </ul>
              ) : null}
              <div
                style={{
                  display: "flex",
                  gap: "0.4rem",
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <form action={acceptAction}>
                  <input type="hidden" name="id" value={row.id} />
                  <button
                    type="submit"
                    className="btn btn-solid"
                    data-testid="triage-accept"
                  >
                    Accept
                  </button>
                </form>
                <form action={deferAction}>
                  <input type="hidden" name="id" value={row.id} />
                  <button
                    type="submit"
                    className="btn"
                    data-testid="triage-defer"
                  >
                    Defer
                  </button>
                </form>
                <details>
                  <summary
                    className="btn"
                    style={{
                      cursor: "pointer",
                      listStyle: "none",
                    }}
                    data-testid="triage-reject-toggle"
                  >
                    Reject
                  </summary>
                  <form
                    action={rejectAction}
                    style={{
                      marginTop: "0.4rem",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.4rem",
                    }}
                  >
                    <input type="hidden" name="id" value={row.id} />
                    <textarea
                      name="note"
                      required
                      minLength={20}
                      rows={2}
                      placeholder="Why are we overruling the agent? (min 20 chars)"
                      style={{
                        background: "var(--stone-light, #111)",
                        color: "var(--text, #eee)",
                        border: "1px solid var(--border, #333)",
                        borderRadius: 3,
                        padding: "0.5rem",
                        fontFamily: "'EB Garamond', serif",
                      }}
                    />
                    <button
                      type="submit"
                      className="btn btn-solid"
                      data-testid="triage-reject-submit"
                    >
                      Reject recommendation
                    </button>
                  </form>
                </details>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
