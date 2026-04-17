"use client";

import { useMemo, useState } from "react";

import type { PublicConclusion } from "@/lib/types";

const KINDS = [
  { id: "counter_evidence", label: "Counter-evidence" },
  { id: "counter_argument", label: "Counter-argument" },
  { id: "clarification", label: "Clarification request" },
  { id: "agreement_extension", label: "Agreement with extension" },
] as const;

export default function RespondForm({ conclusions }: { conclusions: PublicConclusion[] }) {
  const portal = process.env.NEXT_PUBLIC_PORTAL_API?.replace(/\/+$/, "") ?? "";
  const [publishedId, setPublishedId] = useState(conclusions[0]?.id ?? "");
  const [kind, setKind] = useState<string>(KINDS[0].id);
  const [body, setBody] = useState("");
  const [email, setEmail] = useState("");
  const [orcid, setOrcid] = useState("");
  const [citationUrl, setCitationUrl] = useState("");
  const [pseudonymous, setPseudonymous] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const endpoint = useMemo(() => `${portal}/api/public/responses`, [portal]);

  async function submit() {
    setMsg(null);
    if (!portal) {
      setMsg("Set NEXT_PUBLIC_PORTAL_API to your Theseus Codex origin (example: http://localhost:3000).");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          publishedConclusionId: publishedId,
          kind,
          body,
          citationUrl,
          submitterEmail: email,
          orcid,
          pseudonymous: pseudonymous,
        }),
      });
      const json = (await res.json().catch(() => ({}))) as { error?: string; ok?: boolean };
      if (!res.ok) {
        setMsg(json.error || `Submit failed (${res.status})`);
        return;
      }
      setMsg("Submitted. It will be reviewed before it can appear publicly.");
      setBody("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      {!portal ? (
        <p className="muted" style={{ marginTop: 0 }}>
          This static site does not host write APIs. Configure <code>NEXT_PUBLIC_PORTAL_API</code> at build time so the
          form can POST to the Theseus Codex moderation queue.
        </p>
      ) : (
        <p className="muted" style={{ marginTop: 0 }}>
          Posts to <code>{endpoint}</code>
        </p>
      )}

      <label className="muted" style={{ fontSize: "0.9rem", display: "block", marginTop: "0.75rem" }}>
        Conclusion revision (published row id)
        <select
          value={publishedId}
          onChange={(e) => setPublishedId(e.target.value)}
          style={{ display: "block", width: "100%", marginTop: "0.35rem", padding: "0.5rem" }}
        >
          {conclusions.map((c) => (
            <option key={c.id} value={c.id}>
              {c.slug} v{c.version} — {c.publishedAt.slice(0, 10)}
            </option>
          ))}
        </select>
      </label>

      <label className="muted" style={{ fontSize: "0.9rem", display: "block", marginTop: "0.75rem" }}>
        Response type
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          style={{ display: "block", width: "100%", marginTop: "0.35rem", padding: "0.5rem" }}
        >
          {KINDS.map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </select>
      </label>

      <label className="muted" style={{ fontSize: "0.9rem", display: "block", marginTop: "0.75rem" }}>
        Claim (min 20 chars)
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={7} style={{ display: "block", width: "100%", marginTop: "0.35rem", padding: "0.5rem" }} />
      </label>

      <label className="muted" style={{ fontSize: "0.9rem", display: "block", marginTop: "0.75rem" }}>
        Optional citation URL
        <input value={citationUrl} onChange={(e) => setCitationUrl(e.target.value)} style={{ display: "block", width: "100%", marginTop: "0.35rem", padding: "0.5rem" }} />
      </label>

      <label className="muted" style={{ fontSize: "0.9rem", display: "block", marginTop: "0.75rem" }}>
        Email (required; anonymity is not supported)
        <input value={email} onChange={(e) => setEmail(e.target.value)} style={{ display: "block", width: "100%", marginTop: "0.35rem", padding: "0.5rem" }} />
      </label>

      <label className="muted" style={{ fontSize: "0.9rem", display: "block", marginTop: "0.75rem" }}>
        ORCID (optional)
        <input value={orcid} onChange={(e) => setOrcid(e.target.value)} style={{ display: "block", width: "100%", marginTop: "0.35rem", padding: "0.5rem" }} />
      </label>

      <label style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.75rem" }} className="muted">
        <input type="checkbox" checked={pseudonymous} onChange={(e) => setPseudonymous(e.target.checked)} />
        Publish under a pseudonym if approved (still requires verified email; flagged publicly)
      </label>

      {msg ? <p style={{ marginTop: "0.85rem" }}>{msg}</p> : null}

      <div style={{ marginTop: "0.85rem" }}>
        <button type="button" className="btn" disabled={busy} onClick={() => void submit()}>
          {busy ? "Submitting…" : "Submit for moderation"}
        </button>
      </div>
    </div>
  );
}
