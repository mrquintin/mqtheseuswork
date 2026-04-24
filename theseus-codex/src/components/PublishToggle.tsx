"use client";

import { useState } from "react";

/**
 * Inline publish/unpublish control for the dashboard upload list.
 *
 * States:
 *   - unpublished  → button reads "Publish"; click POSTs publish=true.
 *   - published    → button reads "Unpublish"; click POSTs publish=false.
 *   - in-flight    → disabled + "…"; prevents double-click.
 *   - errored      → flips back to the previous state, tooltip shows
 *                    the message.
 *
 * A `publishedAt` prop is passed in (server-side row). We mirror it
 * into local state for immediate feedback; on success we update and
 * re-render; on error we roll back.
 */

export default function PublishToggle({
  uploadId,
  initialPublishedAt,
  initialSlug,
}: {
  uploadId: string;
  initialPublishedAt: Date | string | null;
  initialSlug: string | null;
}) {
  const [publishedAt, setPublishedAt] = useState<Date | string | null>(
    initialPublishedAt,
  );
  const [slug, setSlug] = useState<string | null>(initialSlug);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string>("");

  const isPublished = Boolean(publishedAt);

  async function toggle() {
    setState("loading");
    setError("");
    const prevPublishedAt = publishedAt;
    const prevSlug = slug;
    try {
      const res = await fetch("/api/publish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          upload_id: uploadId,
          publish: !isPublished,
        }),
      });
      const data = (await res.json()) as {
        ok?: boolean;
        slug?: string | null;
        publishedAt?: string | null;
        publicUrl?: string | null;
        error?: string;
      };
      if (!res.ok || !data.ok) {
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      setPublishedAt(data.publishedAt ?? null);
      setSlug(data.slug ?? null);
      setState("idle");
    } catch (e) {
      // Roll back optimistic state if the request failed.
      setPublishedAt(prevPublishedAt);
      setSlug(prevSlug);
      setError(e instanceof Error ? e.message : String(e));
      setState("error");
      setTimeout(() => setState("idle"), 2500);
    }
  }

  const label =
    state === "loading"
      ? "…"
      : state === "error"
        ? `⚠ ${error.slice(0, 30)}`
        : isPublished
          ? "Unpublish"
          : "Publish";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      {isPublished && slug ? (
        <a
          href={`/post/${slug}`}
          target="_blank"
          rel="noopener noreferrer"
          className="mono"
          style={{
            fontSize: "0.58rem",
            letterSpacing: "0.2em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            textDecoration: "none",
            padding: "0.15rem 0.45rem",
            border: "1px solid var(--amber-dim)",
            borderRadius: "2px",
          }}
          title={`View the live post at /post/${slug}`}
        >
          View →
        </a>
      ) : null}
      <button
        type="button"
        onClick={toggle}
        disabled={state === "loading"}
        className="mono"
        style={{
          background: "transparent",
          color: state === "error" ? "var(--ember)" : "var(--amber)",
          border: `1px solid ${
            state === "error" ? "var(--ember)" : "var(--amber-dim)"
          }`,
          padding: "0.22rem 0.55rem",
          fontSize: "0.58rem",
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          cursor: state === "loading" ? "wait" : "pointer",
          borderRadius: "2px",
          transition: "all 0.18s ease",
        }}
        title={
          isPublished
            ? `Currently public at /post/${slug}. Click to hide.`
            : "Make this upload visible on the public blog."
        }
      >
        {label}
      </button>
    </div>
  );
}
