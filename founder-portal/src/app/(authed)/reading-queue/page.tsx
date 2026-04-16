import { fetchReadingQueue } from "@/lib/noosphereLiteratureBridge";
import ReadingQueueClient from "./ReadingQueueClient";

export default async function ReadingQueuePage() {
  const { rows, message } = await fetchReadingQueue();

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", letterSpacing: "0.08em" }}>
        Reading queue
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
        Items are appended when session research generation succeeds; each row must reference a retrieved claim id from
        the hybrid index. Update status after you inspect the source.
      </p>
      {message && rows.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>{message}</p>
      ) : null}
      <ReadingQueueClient initialRows={rows} />
    </main>
  );
}
