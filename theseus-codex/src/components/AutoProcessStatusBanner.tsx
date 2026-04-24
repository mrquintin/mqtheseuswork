"use client";

import { useEffect, useState } from "react";

/**
 * Dashboard banner that surfaces the live state of auto-processing.
 *
 * Three states:
 *   - `loading`      → nothing rendered (brief; we don't want flicker)
 *   - `configured`   → small green pill in the corner: "AUTO-PROCESS ACTIVE"
 *   - `unconfigured` → prominent amber card with the exact setup steps,
 *                      pulled from the live /api/health/auto-processing
 *                      response so the copy tracks reality.
 *
 * Only shown to logged-in founders. Quietly fails if the health endpoint
 * returns 401/500 — we don't want this banner to block the dashboard
 * from rendering for an observability reason.
 */

interface HealthResponse {
  configured: boolean;
  summary: string;
  vercel: {
    github_dispatch_token: boolean;
    github_dispatch_repo: string;
    openai_key: boolean;
  };
  github: {
    workflow_url: string;
  };
}

export default function AutoProcessStatusBanner() {
  const [state, setState] = useState<"loading" | "ok" | "todo">("loading");
  const [data, setData] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/health/auto-processing")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d: HealthResponse) => {
        if (cancelled) return;
        setData(d);
        setState(d.configured ? "ok" : "todo");
      })
      .catch(() => {
        if (!cancelled) setState("ok"); // fail-quiet: hide the banner
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "loading") return null;

  if (state === "ok") {
    return (
      <div
        className="mono"
        style={{
          display: "inline-flex",
          gap: "0.4rem",
          alignItems: "center",
          fontSize: "0.58rem",
          letterSpacing: "0.25em",
          textTransform: "uppercase",
          color: "var(--success, #4ade80)",
          border: "1px solid var(--success, #4ade80)",
          padding: "0.2rem 0.55rem",
          borderRadius: "3px",
          marginBottom: "0.75rem",
        }}
        title={data?.summary || ""}
      >
        <span style={{ fontSize: "0.7rem" }}>●</span>
        <span>Auto-process active</span>
      </div>
    );
  }

  // Unconfigured: show the full setup card.
  return (
    <div
      className="portal-card"
      style={{
        border: "1px solid var(--amber)",
        background:
          "linear-gradient(180deg, rgba(212,160,23,0.06), rgba(212,160,23,0.02))",
        padding: "1rem 1.25rem",
        marginBottom: "1.5rem",
      }}
    >
      <div
        className="mono"
        style={{
          color: "var(--amber)",
          fontSize: "0.6rem",
          letterSpacing: "0.3em",
          textTransform: "uppercase",
          marginBottom: "0.5rem",
        }}
      >
        ⚡ Auto-processing not configured
      </div>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          color: "var(--parchment)",
          fontSize: "0.95rem",
          lineHeight: 1.5,
          margin: "0 0 0.75rem",
        }}
      >
        Uploads currently land in <code>queued_offline</code> and wait.
        Complete the two-minute setup to have every upload auto-analyze
        by Noosphere within ~1 minute:
      </p>
      <ol
        style={{
          fontFamily: "'EB Garamond', serif",
          color: "var(--parchment-dim)",
          fontSize: "0.88rem",
          lineHeight: 1.55,
          margin: "0 0 0.5rem 1.2rem",
          paddingLeft: 0,
        }}
      >
        <li>
          <strong>Vercel →</strong> Settings → Environment Variables → add{" "}
          <code>GITHUB_DISPATCH_TOKEN</code>{" "}
          (a GitHub PAT with <code>repo</code> scope).
          Redeploy.
        </li>
        <li>
          <strong>GitHub →</strong> repo Settings → Secrets and variables →
          Actions → add <code>CODEX_DATABASE_URL</code> (Supabase DIRECT
          connection, port 5432) and optionally{" "}
          <code>OPENAI_API_KEY</code>.
        </li>
      </ol>
      <div
        style={{
          display: "flex",
          gap: "0.75rem",
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <a
          href={data?.github.workflow_url || "#"}
          target="_blank"
          rel="noopener noreferrer"
          className="mono"
          style={{
            color: "var(--amber)",
            fontSize: "0.65rem",
            letterSpacing: "0.2em",
            textTransform: "uppercase",
            textDecoration: "underline",
          }}
        >
          View workflow runs →
        </a>
        <span
          className="mono"
          style={{
            fontSize: "0.62rem",
            letterSpacing: "0.15em",
            color: "var(--parchment-dim)",
          }}
        >
          See <code>docs/Auto_Processing_Setup.md</code> for the full playbook.
        </span>
      </div>
    </div>
  );
}
