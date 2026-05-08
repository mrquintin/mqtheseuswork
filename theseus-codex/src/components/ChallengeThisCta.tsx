"use client";

/**
 * Challenge-this affordance — the explicit invitation channel for
 * outside experts to critique a specific firm conclusion.
 *
 * Distinct from `RespondForm` (general reader responses): the form
 * here demands a *targeted* claim, *concrete* counter-evidence, the
 * *method* the critic used to derive the counter-evidence, and
 * citations. The output lands in the `CritiqueSubmission` moderation
 * queue (see `src/lib/critiquesApi.ts`).
 */

import { useState } from "react";

export type ChallengeThisCtaProps = {
  articleSlug: string;
  publishedConclusionId?: string | null;
  conclusionTitle?: string;
};

export default function ChallengeThisCta({
  articleSlug,
  publishedConclusionId,
  conclusionTitle,
}: ChallengeThisCtaProps) {
  const [open, setOpen] = useState(false);
  const [targetClaim, setTargetClaim] = useState("");
  const [counterEvidence, setCounterEvidence] = useState("");
  const [derivationMethod, setDerivationMethod] = useState("");
  const [citations, setCitations] = useState("");
  const [submitterEmail, setSubmitterEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [publicUrl, setPublicUrl] = useState("");
  const [bio, setBio] = useState("");
  const [orcid, setOrcid] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function submit() {
    setMsg(null);
    setBusy(true);
    try {
      const res = await fetch("/api/public/critique/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          articleSlug,
          publishedConclusionId: publishedConclusionId ?? null,
          targetClaim,
          counterEvidence,
          derivationMethod,
          citations,
          submitterEmail,
          displayName,
          publicUrl,
          bio,
          orcid,
        }),
      });
      const json = (await res.json().catch(() => ({}))) as { error?: string; ok?: boolean };
      if (!res.ok) {
        setMsg(json.error || `Submit failed (${res.status})`);
        return;
      }
      setMsg(
        "Critique recorded. The firm's moderators will respond. Accepted critiques are credited and severe critiques carry a $500 bounty (see /critiques for the rubric).",
      );
      setTargetClaim("");
      setCounterEvidence("");
      setDerivationMethod("");
      setCitations("");
    } catch (error) {
      setMsg(error instanceof Error ? error.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      style={{
        borderTop: "1px solid var(--stroke)",
        borderBottom: "1px solid var(--stroke)",
        margin: "1.6rem 0",
        padding: "1rem 0",
      }}
    >
      <summary
        className="mono"
        style={{
          border: "1px solid var(--amber)",
          color: "var(--amber)",
          cursor: "pointer",
          display: "inline-flex",
          fontSize: "0.66rem",
          letterSpacing: "0.22em",
          padding: "0.6rem 0.85rem",
          textTransform: "uppercase",
        }}
      >
        Challenge this conclusion
      </summary>
      <div className="public-card public-form-card" style={{ marginTop: "1rem" }}>
        <p className="public-muted">
          Targeted critique only. Tell us which specific claim you challenge, what
          counter-evidence you have, and how you derived it. Accepted critiques are
          published with your name and link beside the article. Severe critiques (per the
          rubric on <a href="/critiques">/critiques</a>) carry a $500 bounty — paid to you,
          or donated to a charity you choose.
        </p>
        {conclusionTitle ? (
          <p className="public-muted mono" style={{ fontSize: "0.66rem", letterSpacing: "0.08em" }}>
            Challenging: &apos;{conclusionTitle}&apos;
          </p>
        ) : null}

        <label className="public-label">
          Specific claim being challenged (which sentence / inference?)
          <textarea
            value={targetClaim}
            onChange={(e) => setTargetClaim(e.target.value)}
            rows={2}
          />
        </label>

        <label className="public-label">
          Counter-evidence (what you found that conflicts with the claim)
          <textarea
            value={counterEvidence}
            onChange={(e) => setCounterEvidence(e.target.value)}
            rows={6}
          />
        </label>

        <label className="public-label">
          Method used to derive the counter-evidence (replication, audit, lit review, expert
          opinion, etc.)
          <textarea
            value={derivationMethod}
            onChange={(e) => setDerivationMethod(e.target.value)}
            rows={3}
          />
        </label>

        <label className="public-label">
          Citations (one URL or full reference per line)
          <textarea
            value={citations}
            onChange={(e) => setCitations(e.target.value)}
            rows={3}
          />
        </label>

        <label className="public-label">
          Email (required)
          <input value={submitterEmail} onChange={(e) => setSubmitterEmail(e.target.value)} />
        </label>

        <label className="public-label">
          Display name for credit (optional — defaults to your email&apos;s localpart)
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </label>

        <label className="public-label">
          Public URL — your site, scholar profile, etc. (optional)
          <input value={publicUrl} onChange={(e) => setPublicUrl(e.target.value)} />
        </label>

        <label className="public-label">
          One-line bio for the hall of fame (optional)
          <input value={bio} onChange={(e) => setBio(e.target.value)} />
        </label>

        <label className="public-label">
          ORCID (optional)
          <input value={orcid} onChange={(e) => setOrcid(e.target.value)} />
        </label>

        {msg ? <p>{msg}</p> : null}

        <button type="button" className="btn" disabled={busy} onClick={() => void submit()}>
          {busy ? "Submitting..." : "Submit critique"}
        </button>
      </div>
    </details>
  );
}
