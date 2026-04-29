"use client";

import { useState } from "react";

import type { PublishedConclusion } from "@/lib/conclusionsRead";

const KINDS = [
  { id: "counter_evidence", label: "Counter-evidence" },
  { id: "counter_argument", label: "Counter-argument" },
  { id: "clarification", label: "Clarification request" },
  { id: "agreement_extension", label: "Agreement with extension" },
] as const;

export default function RespondForm({ conclusions }: { conclusions: PublishedConclusion[] }) {
  const [publishedId, setPublishedId] = useState(conclusions[0]?.id ?? "");
  const [kind, setKind] = useState<string>(KINDS[0].id);
  const [body, setBody] = useState("");
  const [email, setEmail] = useState("");
  const [orcid, setOrcid] = useState("");
  const [citationUrl, setCitationUrl] = useState("");
  const [pseudonymous, setPseudonymous] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setMsg(null);
    if (!publishedId) {
      setMsg("No published conclusion is available for response.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/public/responses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          publishedConclusionId: publishedId,
          kind,
          body,
          citationUrl,
          submitterEmail: email,
          orcid,
          pseudonymous,
        }),
      });
      const json = (await res.json().catch(() => ({}))) as { error?: string; ok?: boolean };
      if (!res.ok) {
        setMsg(json.error || `Submit failed (${res.status})`);
        return;
      }
      setMsg("Submitted. It will be reviewed before it can appear publicly.");
      setBody("");
      setCitationUrl("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="public-card public-form-card">
      <p className="public-muted">Responses are reviewed before publication. Engaged responses trigger internal review.</p>

      <label className="public-label">
        Conclusion revision (published row id)
        <select value={publishedId} onChange={(e) => setPublishedId(e.target.value)} disabled={!conclusions.length}>
          {conclusions.length ? (
            conclusions.map((c) => (
              <option key={c.id} value={c.id}>
                {c.slug} v{c.version} - {c.publishedAt.slice(0, 10)}
              </option>
            ))
          ) : (
            <option value="">No published conclusions</option>
          )}
        </select>
      </label>

      <label className="public-label">
        Response type
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </select>
      </label>

      <label className="public-label">
        Claim (min 20 chars)
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={7} />
      </label>

      <label className="public-label">
        Optional citation URL
        <input value={citationUrl} onChange={(e) => setCitationUrl(e.target.value)} />
      </label>

      <label className="public-label">
        Email (required; anonymity is not supported)
        <input value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>

      <label className="public-label">
        ORCID (optional)
        <input value={orcid} onChange={(e) => setOrcid(e.target.value)} />
      </label>

      <label className="public-checkbox">
        <input type="checkbox" checked={pseudonymous} onChange={(e) => setPseudonymous(e.target.checked)} />
        Publish under a pseudonym if approved (still requires verified email; flagged publicly)
      </label>

      {msg ? <p>{msg}</p> : null}

      <button type="button" className="btn" disabled={busy || !publishedId} onClick={() => void submit()}>
        {busy ? "Submitting..." : "Submit for moderation"}
      </button>
    </div>
  );
}
