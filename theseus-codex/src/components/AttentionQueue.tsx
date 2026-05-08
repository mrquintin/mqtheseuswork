import AttentionItem, {
  type AttentionItemViewModel,
} from "./AttentionItem";
import {
  ATTENTION_QUEUE_LABELS,
  type AttentionQueueId,
} from "@/lib/attentionShared";

/**
 * Primary surface of the founder dashboard — the unified attention
 * queue. The list is server-rendered with the ranked items already
 * resolved by `listAttentionForFounder`; each row owns its own
 * snooze/dismiss interaction (see `AttentionItem`).
 *
 * `dismissalRates` is the tuning signal: when a particular queue is
 * collecting an unusual number of dismissals it almost certainly
 * needs threshold adjustment, and the dashboard should make that
 * legible without forcing the founder to dig through audit logs.
 */
export type AttentionQueueProps = {
  items: AttentionItemViewModel[];
  dismissalRates?: Array<{ queue: AttentionQueueId; count: number }>;
  generatedAt?: string;
};

export default function AttentionQueue({
  items,
  dismissalRates = [],
  generatedAt,
}: AttentionQueueProps) {
  const total = items.length;
  return (
    <section
      data-testid="attention-queue"
      aria-label="Unified founder attention queue"
      style={{
        border: "1px solid var(--gold)",
        borderRadius: 2,
        padding: "1rem 1.25rem",
        marginBottom: "1.5rem",
        background: "rgba(205, 151, 67, 0.04)",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: "1rem",
          marginBottom: "0.75rem",
          flexWrap: "wrap",
        }}
      >
        <h2
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "0.95rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--amber)",
            margin: 0,
          }}
        >
          Attention · {total}
        </h2>
        {generatedAt ? (
          <span
            className="mono"
            style={{
              fontSize: "0.6rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
            }}
          >
            ranked by severity → age
          </span>
        ) : null}
      </header>

      {total === 0 ? (
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            color: "var(--parchment)",
            margin: 0,
          }}
        >
          Nihil restat — every queue is empty.
        </p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {items.map((item) => (
            <AttentionItem
              key={`${item.queue}::${item.itemId}`}
              item={item}
            />
          ))}
        </ul>
      )}

      {dismissalRates.length > 0 ? (
        <DismissalRateHint rates={dismissalRates} />
      ) : null}
    </section>
  );
}

function DismissalRateHint({
  rates,
}: {
  rates: Array<{ queue: AttentionQueueId; count: number }>;
}) {
  // Highlight any queue that has accumulated >=5 dismissals in the
  // last 30 days; that's the "this queue needs tuning" signal.
  const noisy = rates.filter((row) => row.count >= 5);
  if (noisy.length === 0) return null;
  return (
    <div
      data-testid="attention-dismissal-hint"
      style={{
        marginTop: "0.75rem",
        padding: "0.6rem 0.8rem",
        borderTop: "1px dashed var(--gold-dim, rgba(205,151,67,0.25))",
        fontSize: "0.72rem",
        color: "var(--parchment-dim)",
      }}
    >
      <span
        className="mono"
        style={{
          letterSpacing: "0.22em",
          textTransform: "uppercase",
          color: "var(--ember)",
        }}
      >
        Tuning signal —
      </span>{" "}
      heavy dismissal rate on:{" "}
      {noisy
        .map((row) => `${ATTENTION_QUEUE_LABELS[row.queue]} (${row.count})`)
        .join(", ")}
      .
    </div>
  );
}
