"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  founderDisplayName,
  type FounderDisplayFields,
} from "@/lib/founderDisplay";

/**
 * /library client component.
 *
 * Pulls the full org-wide inventory via `GET /api/library`, renders
 * one row per upload, and offers three inline actions:
 *
 *   * youOwn            → "Delete" button (confirmation prompt, then
 *                          POST /api/uploads/:id/delete).
 *   * !youOwn, no req   → "Request deletion" button (opens a reason
 *                          prompt, POST /api/deletion-requests).
 *   * !youOwn, has req  → "Cancel request" button (DELETE
 *                          /api/deletion-requests/:reqId).
 *
 * The pending-requests *inbox* (requests targeting your uploads) is
 * rendered as a sibling panel at the top so owners see their queue
 * immediately on arrival. Accept/decline fire
 * PATCH /api/deletion-requests/:id.
 *
 * State strategy: after every mutating call we re-fetch the library
 * and the requests inbox. That's ~20ms extra per action but keeps
 * rendering simple and guarantees both panels stay in sync. If this
 * gets heavy we can move to optimistic updates later.
 */

interface LibraryRow {
  id: string;
  title: string;
  originalName: string;
  sourceType: string;
  mimeType: string;
  fileSize: number;
  status: string;
  errorMessage: string | null;
  extractionMethod: string | null;
  publishedAt: string | null;
  slug: string | null;
  visibility: string;
  createdAt: string;
  founderId: string;
  founder: FounderDisplayFields & { id: string };
  youOwn: boolean;
  yourPendingRequestId: string | null;
  deletionRequests: Array<{
    id: string;
    status: string;
    reason: string | null;
    createdAt: string;
    requesterId: string;
    requester: FounderDisplayFields & { id: string };
  }>;
}

interface IncomingRequest {
  id: string;
  reason: string | null;
  createdAt: string;
  requester: FounderDisplayFields & { id: string };
  upload: {
    id: string;
    title: string;
    originalName: string;
    createdAt: string;
  };
}

interface OutgoingRequest {
  id: string;
  status: string;
  reason: string | null;
  decision: string | null;
  createdAt: string;
  respondedAt: string | null;
  upload: {
    id: string;
    title: string;
    founder: FounderDisplayFields & { id: string };
    deletedAt: string | null;
  };
}

interface LibraryState {
  you: { id: string; name: string } | null;
  rows: LibraryRow[];
  incoming: IncomingRequest[];
  outgoing: OutgoingRequest[];
  loading: boolean;
  error: string;
}

export default function LibraryBrowser() {
  const [state, setState] = useState<LibraryState>({
    you: null,
    rows: [],
    incoming: [],
    outgoing: [],
    loading: true,
    error: "",
  });
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [publishedFilter, setPublishedFilter] = useState<"all" | "published">(
    "all",
  );

  const reload = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query.trim());
      if (statusFilter) params.set("status", statusFilter);
      if (publishedFilter === "published") params.set("published", "1");
      const [libRes, reqRes] = await Promise.all([
        fetch(`/api/library?${params.toString()}`),
        fetch("/api/deletion-requests"),
      ]);
      if (!libRes.ok) throw new Error(`library ${libRes.status}`);
      if (!reqRes.ok) throw new Error(`requests ${reqRes.status}`);
      const libData = await libRes.json();
      const reqData = await reqRes.json();
      setState({
        you: libData.you,
        rows: libData.rows,
        incoming: reqData.incoming,
        outgoing: reqData.outgoing,
        loading: false,
        error: "",
      });
    } catch (e) {
      setState((s) => ({
        ...s,
        loading: false,
        error: e instanceof Error ? e.message : String(e),
      }));
    }
  }, [query, statusFilter, publishedFilter]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function doDelete(uploadId: string, title: string) {
    const reason = window.prompt(
      `Delete "${title}"? This soft-deletes the row (recoverable in the DB) and removes it from the blog + Codex. Optionally add a note:`,
      "",
    );
    if (reason === null) return; // cancelled
    const res = await fetch(`/api/upload/${uploadId}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      alert(`Delete failed: ${d.error || res.status}`);
      return;
    }
    await reload();
  }

  async function doRequest(uploadId: string, title: string, ownerName: string) {
    const reason = window.prompt(
      `Ask ${ownerName} to delete "${title}"? Type a reason — the owner sees it before deciding.`,
      "",
    );
    if (reason === null) return;
    const res = await fetch("/api/deletion-requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: uploadId, reason }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      alert(`Request failed: ${d.error || res.status}`);
      return;
    }
    await reload();
  }

  async function doCancel(reqId: string) {
    if (!window.confirm("Cancel your deletion request?")) return;
    const res = await fetch(`/api/deletion-requests/${reqId}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      alert(`Cancel failed: ${d.error || res.status}`);
      return;
    }
    await reload();
  }

  async function doDecide(
    reqId: string,
    action: "accept" | "decline",
    title: string,
  ) {
    const note = window.prompt(
      action === "accept"
        ? `Accept this request and delete "${title}"? Optional note to the requester:`
        : `Decline this request for "${title}"? Optional note explaining why:`,
      "",
    );
    if (note === null) return;
    const res = await fetch(`/api/deletion-requests/${reqId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, decision: note }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      alert(`Action failed: ${d.error || res.status}`);
      return;
    }
    await reload();
  }

  if (state.loading) {
    return (
      <p
        className="mono"
        style={{ color: "var(--amber-dim)", letterSpacing: "0.2em" }}
      >
        Loading library…
      </p>
    );
  }
  if (state.error) {
    return (
      <p style={{ color: "var(--ember)" }}>Error loading library: {state.error}</p>
    );
  }

  return (
    <div>
      {/* Inbox: pending requests targeting your uploads */}
      {state.incoming.length > 0 ? (
        <section
          id="requests"
          style={{
            marginBottom: "2rem",
            padding: "1rem 1.25rem",
            border: "1px solid var(--amber)",
            borderRadius: "4px",
            background:
              "linear-gradient(180deg, rgba(212,160,23,0.08), rgba(212,160,23,0.02))",
          }}
        >
          <h3
            className="mono"
            style={{
              fontSize: "0.65rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber)",
              margin: "0 0 0.75rem",
            }}
          >
            {state.incoming.length} Deletion request
            {state.incoming.length === 1 ? "" : "s"} awaiting your decision
          </h3>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {state.incoming.map((r) => (
              <li
                key={r.id}
                style={{
                  padding: "0.8rem 0",
                  borderTop: "1px solid var(--stroke)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    gap: "0.75rem",
                    flexWrap: "wrap",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <div style={{ flex: "1 1 auto", minWidth: "240px" }}>
                    <p
                      style={{
                        margin: "0 0 0.2rem",
                        color: "var(--parchment)",
                        fontFamily: "'EB Garamond', serif",
                        fontSize: "1.05rem",
                      }}
                    >
                      <strong>{founderDisplayName(r.requester)}</strong>
                      <span style={{ color: "var(--parchment-dim)" }}>
                        {" "}
                        asks to delete{" "}
                      </span>
                      <em>“{r.upload.title}”</em>
                    </p>
                    {r.reason ? (
                      <p
                        className="mono"
                        style={{
                          margin: 0,
                          fontSize: "0.72rem",
                          color: "var(--parchment-dim)",
                          letterSpacing: "0.06em",
                          lineHeight: 1.4,
                        }}
                      >
                        Reason: {r.reason}
                      </p>
                    ) : null}
                    <p
                      className="mono"
                      style={{
                        fontSize: "0.58rem",
                        letterSpacing: "0.2em",
                        color: "var(--amber-dim)",
                        margin: "0.3rem 0 0",
                        textTransform: "uppercase",
                      }}
                    >
                      {new Date(r.createdAt).toLocaleDateString()}
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: "0.4rem" }}>
                    <button
                      type="button"
                      className="mono"
                      onClick={() => doDecide(r.id, "accept", r.upload.title)}
                      style={decideBtn("accept")}
                    >
                      Accept & delete
                    </button>
                    <button
                      type="button"
                      className="mono"
                      onClick={() => doDecide(r.id, "decline", r.upload.title)}
                      style={decideBtn("decline")}
                    >
                      Decline
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Filters */}
      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 4,
          background: "var(--stone-black, #0a0a0a)",
          padding: "0.5rem 0 0.7rem",
          marginBottom: "0.9rem",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          gap: "0.4rem",
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search title / filename / description…"
          style={{
            flex: "1 1 14rem",
            minWidth: 0,
            padding: "0.35rem 0.6rem",
            fontSize: "0.85rem",
            background: "transparent",
            border: "1px solid var(--border)",
            color: "var(--parchment)",
            borderRadius: 2,
          }}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{ flex: "0 0 auto", fontSize: "0.78rem" }}
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="processing">Analyzing</option>
          <option value="queued_offline">Queued offline</option>
          <option value="ingested">Analyzed</option>
          <option value="failed">Failed</option>
        </select>
        <select
          value={publishedFilter}
          onChange={(e) =>
            setPublishedFilter(e.target.value as "all" | "published")
          }
          style={{ flex: "0 0 auto", fontSize: "0.78rem" }}
        >
          <option value="all">All visibility</option>
          <option value="published">Published only</option>
        </select>
      </div>

      {/* Library table */}
      {state.rows.length === 0 ? (
        <div
          className="portal-card"
          style={{
            padding: "1.25rem",
            textAlign: "center",
            color: "var(--parchment-dim)",
            fontSize: "0.9rem",
          }}
        >
          No uploads match the current filters.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {state.rows.map((row) => (
            <li
              key={row.id}
              className="portal-card"
              style={{
                padding: "1rem 1.2rem",
                marginBottom: "0.8rem",
                borderLeft: `3px solid ${
                  row.youOwn ? "var(--amber)" : "var(--stroke)"
                }`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: "1rem",
                  alignItems: "flex-start",
                  flexWrap: "wrap",
                  justifyContent: "space-between",
                }}
              >
                <div style={{ flex: "1 1 300px", minWidth: 0 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      overflow: "hidden",
                    }}
                  >
                    <Link
                      href={`/upload/${row.id}`}
                      style={{
                        fontFamily: "'EB Garamond', serif",
                        fontSize: "1.12rem",
                        color: "var(--parchment)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        textDecoration: "none",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {row.title}
                    </Link>
                    {row.visibility === "private" ? (
                      <span
                        className="mono"
                        title="Private — only you see this row. Noosphere still analyses it for your own conclusions."
                        style={{
                          fontSize: "0.54rem",
                          letterSpacing: "0.22em",
                          textTransform: "uppercase",
                          color: "var(--amber)",
                          border: "1px solid var(--amber-dim)",
                          padding: "0.12rem 0.45rem",
                          borderRadius: "2px",
                          flexShrink: 0,
                        }}
                      >
                        Private
                      </span>
                    ) : row.visibility === "semi-private" ? (
                      // Semi-private: visible here so the whole firm
                      // can read it, but the "Publish as blog post"
                      // toggle is blocked and the public blog + any
                      // /post/<slug> route filter this row out. Same
                      // badge visual as Private so the eye catches
                      // "this is constrained" at a glance, but the
                      // title hover spells out the firm-level
                      // difference.
                      <span
                        className="mono"
                        title="Semi-private — every founder sees this in /library, but the public blog never does. Noosphere still analyses it for firm conclusions. Publishing is blocked until visibility is flipped back."
                        style={{
                          fontSize: "0.54rem",
                          letterSpacing: "0.22em",
                          textTransform: "uppercase",
                          color: "var(--amber)",
                          border: "1px solid var(--amber-dim)",
                          padding: "0.12rem 0.45rem",
                          borderRadius: "2px",
                          flexShrink: 0,
                        }}
                      >
                        Semi-private
                      </span>
                    ) : null}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "0.35rem",
                      alignItems: "center",
                      marginTop: "0.35rem",
                    }}
                  >
                    <span
                      className="mono"
                      title={`Source type: ${describeSourceType(row.sourceType, row.mimeType)}`}
                      style={{
                        fontSize: "0.54rem",
                        letterSpacing: "0.2em",
                        textTransform: "uppercase",
                        color: "var(--parchment)",
                        border: "1px solid var(--border)",
                        background: "var(--stone-mid)",
                        padding: "0.12rem 0.45rem",
                        borderRadius: 2,
                      }}
                    >
                      {sourceTypePill(row.sourceType, row.mimeType)}
                    </span>
                    <span
                      className={`badge badge-${badgeForStatus(row.status)}`}
                      title={
                        row.status === "failed" && row.errorMessage
                          ? row.errorMessage
                          : `Analysis status: ${row.status}`
                      }
                      style={{ fontSize: "0.54rem", padding: "0.12rem 0.45rem" }}
                    >
                      {analysisLabel(row.status)}
                    </span>
                    {row.publishedAt ? (
                      <span
                        className="mono"
                        style={{
                          fontSize: "0.54rem",
                          letterSpacing: "0.2em",
                          textTransform: "uppercase",
                          color: "var(--success)",
                          border: "1px solid var(--success)",
                          padding: "0.12rem 0.45rem",
                          borderRadius: 2,
                        }}
                      >
                        Published
                      </span>
                    ) : null}
                  </div>
                  <div
                    className="mono"
                    style={{
                      fontSize: "0.6rem",
                      letterSpacing: "0.1em",
                      color: "var(--parchment-dim)",
                      marginTop: "0.35rem",
                    }}
                  >
                    {founderDisplayName(row.founder)}
                    {row.youOwn ? (
                      <span style={{ color: "var(--amber)" }}> (you)</span>
                    ) : null}
                    {" · "}
                    {new Date(row.createdAt).toLocaleDateString()}
                    {" · "}
                    {(row.fileSize / 1024).toFixed(0)} KB
                  </div>
                  {row.status === "failed" && row.errorMessage ? (
                    <p
                      style={{
                        margin: "0.4rem 0 0",
                        fontSize: "0.75rem",
                        color: "var(--ember)",
                        lineHeight: 1.45,
                      }}
                    >
                      Analysis failed: {row.errorMessage.slice(0, 200)}
                    </p>
                  ) : null}
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: "0.4rem",
                    alignItems: "center",
                    flexShrink: 0,
                    flexWrap: "wrap",
                    justifyContent: "flex-end",
                  }}
                >
                  {row.youOwn ? (
                    <>
                      <button
                        type="button"
                        className="mono"
                        onClick={() => doDelete(row.id, row.title)}
                        style={ghostBtn("ember")}
                        title="Only you can delete your own uploads."
                      >
                        Delete
                      </button>
                      {row.deletionRequests.length > 0 ? (
                        <span
                          className="mono"
                          style={{
                            fontSize: "0.58rem",
                            letterSpacing: "0.18em",
                            color: "var(--amber)",
                            border: "1px solid var(--amber)",
                            padding: "0.2rem 0.5rem",
                            borderRadius: "2px",
                          }}
                          title={`${row.deletionRequests.length} pending request(s)`}
                        >
                          {row.deletionRequests.length} req
                        </span>
                      ) : null}
                    </>
                  ) : row.yourPendingRequestId ? (
                    <button
                      type="button"
                      className="mono"
                      onClick={() => doCancel(row.yourPendingRequestId!)}
                      style={ghostBtn("muted")}
                    >
                      Cancel request
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="mono"
                      onClick={() =>
                        doRequest(row.id, row.title, founderDisplayName(row.founder))
                      }
                      style={ghostBtn("amber")}
                      title={`Ask ${founderDisplayName(row.founder)} to delete this.`}
                    >
                      Request deletion
                    </button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Outgoing history — useful for remembering what you asked for */}
      {state.outgoing.length > 0 ? (
        <details
          style={{
            marginTop: "2rem",
            padding: "0.75rem 1rem",
            border: "1px solid var(--stroke)",
            borderRadius: "4px",
          }}
        >
          <summary
            className="mono"
            style={{
              fontSize: "0.62rem",
              letterSpacing: "0.25em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              cursor: "pointer",
            }}
          >
            Your deletion-request history · {state.outgoing.length}
          </summary>
          <ul
            style={{
              listStyle: "none",
              margin: "0.8rem 0 0",
              padding: 0,
              fontSize: "0.85rem",
            }}
          >
            {state.outgoing.map((r) => (
              <li
                key={r.id}
                style={{
                  padding: "0.5rem 0",
                  borderTop: "1px solid var(--stroke)",
                  color: "var(--parchment-dim)",
                }}
              >
                <span style={{ color: "var(--parchment)" }}>
                  “{r.upload.title}”
                </span>
                {" · "}
                <span
                  className="mono"
                  style={{
                    color:
                      r.status === "accepted"
                        ? "var(--success, #4ade80)"
                        : r.status === "declined"
                          ? "var(--ember)"
                          : "var(--amber-dim)",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    fontSize: "0.7rem",
                  }}
                >
                  {r.status}
                </span>
                {r.decision ? <span> — {r.decision}</span> : null}
                <span
                  className="mono"
                  style={{
                    fontSize: "0.6rem",
                    color: "var(--amber-dim)",
                    marginLeft: "0.5em",
                    letterSpacing: "0.1em",
                  }}
                >
                  {new Date(r.createdAt).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function sourceTypePill(sourceType: string, mimeType: string): string {
  const st = (sourceType || "").toLowerCase();
  const mt = (mimeType || "").toLowerCase();
  if (st === "audio" || mt.startsWith("audio/")) return "Audio";
  if (st === "podcast") return "Podcast";
  if (st === "dialectic" || st === "session" || st === "transcript")
    return "Transcript";
  if (mt === "application/pdf" || st === "pdf") return "PDF";
  if (st === "annotation") return "Annotation";
  if (st === "external") return "External";
  if (st === "written" || mt.startsWith("text/")) return "Written";
  return st || "File";
}

function describeSourceType(sourceType: string, mimeType: string): string {
  const pill = sourceTypePill(sourceType, mimeType);
  return mimeType ? `${pill} (${mimeType})` : pill;
}

function badgeForStatus(
  status: string,
): "pending" | "processing" | "ingested" | "failed" {
  if (status === "failed") return "failed";
  if (status === "ingested") return "ingested";
  if (
    status === "processing" ||
    status === "extracting" ||
    status === "awaiting_ingest"
  )
    return "processing";
  return "pending";
}

function analysisLabel(status: string): string {
  switch (status) {
    case "ingested":
      return "Analyzed";
    case "processing":
      return "Analyzing";
    case "extracting":
      return "Extracting";
    case "awaiting_ingest":
      return "Awaiting analysis";
    case "queued_offline":
      return "Queued";
    case "failed":
      return "Failed";
    case "pending":
    default:
      return "Pending";
  }
}

function ghostBtn(tone: "amber" | "ember" | "muted"): React.CSSProperties {
  const color =
    tone === "amber"
      ? "var(--amber)"
      : tone === "ember"
        ? "var(--ember)"
        : "var(--parchment-dim)";
  const border =
    tone === "amber"
      ? "var(--amber-dim)"
      : tone === "ember"
        ? "var(--ember)"
        : "var(--stroke)";
  return {
    background: "transparent",
    color,
    border: `1px solid ${border}`,
    padding: "0.25rem 0.65rem",
    fontSize: "0.6rem",
    letterSpacing: "0.18em",
    textTransform: "uppercase",
    cursor: "pointer",
    borderRadius: "2px",
    transition: "all 0.18s ease",
  };
}

function decideBtn(kind: "accept" | "decline"): React.CSSProperties {
  if (kind === "accept") {
    return {
      background: "var(--amber)",
      color: "var(--stone-black, #0a0a0a)",
      border: "1px solid var(--amber)",
      padding: "0.35rem 0.9rem",
      fontSize: "0.6rem",
      letterSpacing: "0.22em",
      textTransform: "uppercase",
      cursor: "pointer",
      borderRadius: "2px",
      fontWeight: 700,
    };
  }
  return {
    background: "transparent",
    color: "var(--parchment)",
    border: "1px solid var(--stroke)",
    padding: "0.35rem 0.9rem",
    fontSize: "0.6rem",
    letterSpacing: "0.22em",
    textTransform: "uppercase",
    cursor: "pointer",
    borderRadius: "2px",
  };
}
