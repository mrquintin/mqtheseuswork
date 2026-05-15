"use client";

import Link from "next/link";

/**
 * Empty / error / stale diagnostic for the Explorer.
 *
 * The Explorer is useless without an embedding index, and the failure
 * modes are distinct enough that one generic "no data" card is a
 * disservice: the index can be *loading*, *warming up* (some
 * conclusions embedded, not yet enough), *empty* (nothing embedded),
 * *stale* (embedded count lags the conclusion count), or the API can
 * be outright *erroring*. Each gets its own headline and remedy.
 *
 * The headline remedy is a one-click "Rebuild index" — but rebuilding
 * the index is a write-class action, so it's gated to founders/admins
 * (`canRebuild`). Viewers see the same diagnostic with a note pointing
 * them at someone who can act.
 */

export type ExplorerIndexStatus =
  | "loading"
  | "warming"
  | "empty"
  | "stale"
  | "error";

interface ExplorerEmptyStateProps {
  status: ExplorerIndexStatus;
  embedded: number;
  total: number;
  message?: string | null;
  /** True when the current founder may trigger a rebuild. */
  canRebuild: boolean;
  /** Invoked by the "Rebuild index" button. */
  onRebuild?: () => void | Promise<void>;
  /** True while a rebuild is in flight. */
  rebuilding?: boolean;
}

const TONE: Record<ExplorerIndexStatus, string> = {
  loading: "var(--info)",
  warming: "var(--amber)",
  empty: "var(--amber)",
  stale: "var(--amber)",
  error: "var(--ember)",
};

const HEADING: Record<ExplorerIndexStatus, string> = {
  loading: "Loading projection…",
  warming: "Embedding index is still warming up",
  empty: "Embedding index is missing",
  stale: "Embedding index is stale",
  error: "Embedding index is unavailable",
};

function describe(
  status: ExplorerIndexStatus,
  embedded: number,
  total: number,
  message?: string | null,
): string {
  switch (status) {
    case "loading":
      return "Fetching the conclusion embeddings.";
    case "warming":
      return `Only ${embedded} of ${total} conclusions are embedded. The Explorer needs at least 3 to project — the next ingest pass will embed the rest, or rebuild the index now to force it.`;
    case "empty":
      return "No conclusions are embedded yet. Add an upload, or rebuild the index to embed the conclusions already in the firm.";
    case "stale":
      return `The index covers ${embedded} of ${total} conclusions — newer conclusions are not in the projection yet. Rebuild to bring it current.`;
    case "error":
      return `The embeddings API returned an error: ${message || "unknown"}. The index may be corrupt; a rebuild often clears it.`;
    default:
      return "";
  }
}

export default function ExplorerEmptyState({
  status,
  embedded,
  total,
  message,
  canRebuild,
  onRebuild,
  rebuilding = false,
}: ExplorerEmptyStateProps) {
  const tone = TONE[status];
  const pct =
    total > 0
      ? Math.max(0, Math.min(100, Math.round((embedded / total) * 100)))
      : 0;
  const showRebuild = status !== "loading";

  return (
    <section
      className="portal-card"
      role={status === "error" ? "alert" : "status"}
      aria-live="polite"
      data-explorer-status={status}
      style={{ padding: "1rem 1.1rem", borderLeft: `3px solid ${tone}` }}
    >
      <div
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          color: tone,
          marginBottom: "0.4rem",
        }}
      >
        Embedding index
      </div>
      <h3
        style={{
          margin: 0,
          fontFamily: "'EB Garamond', serif",
          fontSize: "1.05rem",
          color: "var(--parchment)",
          fontWeight: 500,
        }}
      >
        {HEADING[status]}
      </h3>
      {status !== "loading" ? (
        <p
          style={{
            margin: "0.45rem 0 0",
            fontSize: "0.85rem",
            color: "var(--parchment-dim)",
            lineHeight: 1.5,
          }}
        >
          {describe(status, embedded, total, message)}
        </p>
      ) : null}

      <div
        className="mono"
        style={{
          marginTop: "0.6rem",
          fontSize: "0.7rem",
          color: "var(--parchment)",
          letterSpacing: "0.08em",
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <span>
          embedded {embedded}/{total}
          {total > 0 ? ` (${pct}%)` : ""}
        </span>
        {total > 0 ? (
          <span
            aria-hidden="true"
            style={{
              flex: "1 1 8rem",
              minWidth: "6rem",
              maxWidth: "12rem",
              height: 4,
              background: "var(--stone-mid)",
              borderRadius: 2,
              overflow: "hidden",
            }}
          >
            <span
              style={{
                display: "block",
                width: `${pct}%`,
                height: "100%",
                background: tone,
              }}
            />
          </span>
        ) : null}
      </div>

      {showRebuild ? (
        <div
          style={{
            marginTop: "0.8rem",
            display: "flex",
            gap: "0.5rem",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          {canRebuild ? (
            <button
              type="button"
              className="btn"
              onClick={() => {
                if (!rebuilding) void onRebuild?.();
              }}
              disabled={rebuilding}
              style={{
                fontSize: "0.62rem",
                padding: "0.35rem 0.75rem",
                opacity: rebuilding ? 0.6 : 1,
              }}
            >
              {rebuilding ? "Rebuilding index…" : "Rebuild index"}
            </button>
          ) : (
            <span
              className="mono"
              style={{ fontSize: "0.62rem", color: "var(--parchment-dim)" }}
            >
              Ask a founder to rebuild the index.
            </span>
          )}
          <Link
            href="/upload"
            className="btn"
            style={{
              fontSize: "0.62rem",
              padding: "0.35rem 0.75rem",
              textDecoration: "none",
            }}
          >
            Add an upload
          </Link>
          <Link
            href="/ops"
            className="btn"
            style={{
              fontSize: "0.62rem",
              padding: "0.35rem 0.75rem",
              textDecoration: "none",
            }}
          >
            Open ops console
          </Link>
        </div>
      ) : null}
    </section>
  );
}
