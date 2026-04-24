"use client";

import { useMemo, useState } from "react";

type ReviewRow = {
  id: string;
  status: string;
  checklistJson: string;
  reviewerNotes: string;
  declineReason: string;
  revisionAsk: string;
  reviewerFounderId: string | null;
  createdAt: string;
  updatedAt: string;
  target: {
    id: string;
    text: string;
    topicHint: string;
    confidenceTier: string;
    confidence: number;
    createdAt: string;
  };
  reviewer: { id: string; name: string; username: string } | null;
};

type FirmRow = { id: string; text: string; topicHint: string; createdAt: string };

const CHECKLIST_KEYS = [
  ["metaAnalysisOk", "Five-criterion meta-analysis passed"],
  ["adversarialEngagedOk", "Top adversarial challenges engaged"],
  ["clarityOk", "Publication-ready clarity"],
  ["noLeakageOk", "No private-context leakage"],
  ["noHarmOk", "No inadvertent harms"],
] as const;

export default function PublicationClient({
  reviews,
  firmConclusions,
  currentFounderId,
}: {
  reviews: ReviewRow[];
  firmConclusions: FirmRow[];
  currentFounderId: string;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [enqueueId, setEnqueueId] = useState<string>(firmConclusions[0]?.id ?? "");
  const [openId, setOpenId] = useState<string | null>(reviews[0]?.id ?? null);

  const checklistTemplate = useMemo(() => {
    const o: Record<string, boolean> = {};
    for (const [k] of CHECKLIST_KEYS) o[k] = false;
    return o;
  }, []);

  async function callReview(id: string, body: unknown) {
    setBusyId(id);
    setMessage(null);
    try {
      const res = await fetch(`/api/publication/review/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) {
        setMessage(json.error || `Request failed (${res.status})`);
        return;
      }
      window.location.reload();
    } finally {
      setBusyId(null);
    }
  }

  async function enqueue() {
    if (!enqueueId) return;
    setBusyId("enqueue");
    setMessage(null);
    try {
      const res = await fetch("/api/publication/queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conclusionId: enqueueId }),
      });
      const json = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) {
        setMessage(json.error || `Request failed (${res.status})`);
        return;
      }
      window.location.reload();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {message ? (
        <p style={{ color: "var(--ember)", fontSize: "0.85rem", margin: 0 }} role="status">
          {message}
        </p>
      ) : null}

      <section className="portal-card" style={{ padding: "1rem 1.25rem" }}>
        <h2 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", fontSize: "0.9rem", letterSpacing: "0.12em" }}>
          Enqueue firm conclusion
        </h2>
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
          Only <strong>firm-tier</strong> conclusions may enter review. Meta-analysis, adversarial engagement, and founder
          checklist gates are enforced at publish time.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", marginTop: "0.75rem", alignItems: "center" }}>
          <select
            className="btn"
            style={{ flex: "1 1 320px", background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
            value={enqueueId}
            onChange={(e) => setEnqueueId(e.target.value)}
          >
            <option value="">Select a firm conclusion…</option>
            {firmConclusions.map((c) => (
              <option key={c.id} value={c.id}>
                {(c.topicHint ? `${c.topicHint} · ` : "") + c.text.slice(0, 120)}
                {c.text.length > 120 ? "…" : ""}
              </option>
            ))}
          </select>
          <button type="button" className="btn" disabled={!enqueueId || busyId === "enqueue"} onClick={() => void enqueue()}>
            {busyId === "enqueue" ? "Enqueueing…" : "Enqueue"}
          </button>
          <a className="btn" href="/api/publication/export" style={{ textDecoration: "none", fontSize: "0.65rem" }}>
            Export JSON
          </a>
        </div>
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {reviews.map((r) => {
          const isMine = r.reviewerFounderId === currentFounderId;
          const expanded = openId === r.id;
          let checklist: Record<string, boolean> = { ...checklistTemplate };
          try {
            const parsed = JSON.parse(r.checklistJson || "{}") as Record<string, boolean>;
            checklist = { ...checklistTemplate, ...parsed };
          } catch {
            /* ignore */
          }

          return (
            <article key={r.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                <div style={{ flex: "1 1 420px" }}>
                  <div style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
                    {r.status} · updated {r.updatedAt.slice(0, 10)}
                    {r.reviewer ? ` · reviewer ${r.reviewer.name}` : ""}
                  </div>
                  <p style={{ marginTop: "0.5rem", color: "var(--parchment)" }}>{r.target.text}</p>
                  {r.revisionAsk ? (
                    <p style={{ marginTop: "0.35rem", fontSize: "0.8rem", color: "var(--ember)" }}>
                      Revision ask: {r.revisionAsk}
                    </p>
                  ) : null}
                  {r.declineReason ? (
                    <p style={{ marginTop: "0.35rem", fontSize: "0.8rem", color: "var(--ember)" }}>
                      Declined: {r.declineReason}
                    </p>
                  ) : null}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", alignItems: "flex-start" }}>
                  <button type="button" className="btn" style={{ fontSize: "0.65rem" }} onClick={() => setOpenId(expanded ? null : r.id)}>
                    {expanded ? "Hide actions" : "Actions"}
                  </button>
                </div>
              </div>

              {expanded ? (
                <div style={{ marginTop: "1rem", borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                    {(r.status === "queued" || r.status === "needs_revision") && (
                      <button
                        type="button"
                        className="btn"
                        disabled={busyId === r.id}
                        onClick={() => void callReview(r.id, { action: "claim" })}
                      >
                        {busyId === r.id ? "…" : "Claim review"}
                      </button>
                    )}
                    {r.status === "in_review" && isMine && (
                      <button
                        type="button"
                        className="btn"
                        disabled={busyId === r.id}
                        onClick={() => void callReview(r.id, { action: "release" })}
                      >
                        Release claim
                      </button>
                    )}
                  </div>

                  {r.status === "in_review" && isMine ? (
                    <PublishPanel
                      key={r.id}
                      reviewId={r.id}
                      checklist={checklist}
                      defaultStatedConfidence={r.target.confidence}
                      busy={busyId === r.id}
                      onError={(msg) => setMessage(msg)}
                      onPublish={(payload) => void callReview(r.id, payload)}
                      onNeedsRevision={(revisionAsk) => void callReview(r.id, { action: "needs_revision", revisionAsk })}
                      onDecline={(declineReason) => void callReview(r.id, { action: "decline", declineReason })}
                      onSaveChecklist={(next) => void callReview(r.id, { action: "checklist", checklist: next })}
                    />
                  ) : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </section>
    </div>
  );
}

function PublishPanel({
  reviewId,
  checklist,
  defaultStatedConfidence,
  busy,
  onError,
  onPublish,
  onNeedsRevision,
  onDecline,
  onSaveChecklist,
}: {
  reviewId: string;
  checklist: Record<string, boolean>;
  defaultStatedConfidence: number;
  busy: boolean;
  onError: (msg: string) => void;
  onPublish: (payload: unknown) => void;
  onNeedsRevision: (ask: string) => void;
  onDecline: (reason: string) => void;
  onSaveChecklist: (next: Record<string, boolean>) => void;
}) {
  const [localCheck, setLocalCheck] = useState(checklist);
  const [evidenceSummary, setEvidenceSummary] = useState("");
  const [exitLines, setExitLines] = useState("");
  const [objection, setObjection] = useState("");
  const [firmAnswer, setFirmAnswer] = useState("");
  const [openQs, setOpenQs] = useState("");
  const [voices, setVoices] = useState("");
  const [discounted, setDiscounted] = useState("0.65");
  const [calibReason, setCalibReason] = useState("");
  const [slug, setSlug] = useState("");
  const [revisionAsk, setRevisionAsk] = useState("");
  const [declineReason, setDeclineReason] = useState("");

  return (
    <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <fieldset style={{ border: "1px solid var(--border)", padding: "0.75rem" }}>
        <legend style={{ color: "var(--gold-dim)", fontSize: "0.65rem", letterSpacing: "0.12em" }}>Publication checklist</legend>
        <div style={{ display: "grid", gap: "0.35rem" }}>
          {CHECKLIST_KEYS.map(([k, label]) => (
            <label key={k} style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", gap: "0.5rem" }}>
              <input
                type="checkbox"
                checked={Boolean(localCheck[k])}
                onChange={(e) => setLocalCheck((prev) => ({ ...prev, [k]: e.target.checked }))}
              />
              {label}
            </label>
          ))}
        </div>
        <button type="button" className="btn" style={{ marginTop: "0.5rem", fontSize: "0.65rem" }} disabled={busy} onClick={() => onSaveChecklist(localCheck)}>
          Save checklist draft
        </button>
      </fieldset>

      <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        Evidence summary (public)
        <textarea
          value={evidenceSummary}
          onChange={(e) => setEvidenceSummary(e.target.value)}
          rows={4}
          style={{ width: "100%", background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
        />
      </label>

      <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        Exit conditions / what would change our mind (one per line)
        <textarea
          value={exitLines}
          onChange={(e) => setExitLines(e.target.value)}
          rows={4}
          style={{ width: "100%", background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
        />
      </label>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
        <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          Strongest engaged objection
          <textarea
            value={objection}
            onChange={(e) => setObjection(e.target.value)}
            rows={4}
            style={{ width: "100%", background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
          />
        </label>
        <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          Firm answer
          <textarea
            value={firmAnswer}
            onChange={(e) => setFirmAnswer(e.target.value)}
            rows={4}
            style={{ width: "100%", background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
          />
        </label>
      </div>

      <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        Adjacent open questions (one per line)
        <textarea
          value={openQs}
          onChange={(e) => setOpenQs(e.target.value)}
          rows={3}
          style={{ width: "100%", background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
        />
      </label>

      <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        Voice map (optional) — one per line, e.g. “Habermas: agrees on X; diverges on Y”.
        <textarea
          value={voices}
          onChange={(e) => setVoices(e.target.value)}
          rows={3}
          style={{ width: "100%", background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
        />
      </label>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
        <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          Discounted confidence (0–1)
          <input
            value={discounted}
            onChange={(e) => setDiscounted(e.target.value)}
            style={{ background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
          />
        </label>
        <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          Optional slug override
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            style={{ background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem", minWidth: "240px" }}
          />
        </label>
      </div>

      <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        Calibration discount reason (why headline confidence differs from stated)
        <textarea
          value={calibReason}
          onChange={(e) => setCalibReason(e.target.value)}
          rows={3}
          style={{ width: "100%", background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
        />
      </label>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            const exitConditions = exitLines
              .split("\n")
              .map((s) => s.trim())
              .filter(Boolean);
            const voiceComparisons = voices
              .split("\n")
              .map((line) => line.trim())
              .filter(Boolean)
              .map((line) => {
                const idx = line.indexOf(":");
                if (idx === -1) return { voice: "Note", stance: line };
                return { voice: line.slice(0, idx).trim() || "Voice", stance: line.slice(idx + 1).trim() };
              });
            if (!evidenceSummary.trim()) {
              onError("Evidence summary is required.");
              return;
            }
            if (exitConditions.length === 0) {
              onError("At least one exit condition is required.");
              return;
            }
            if (!objection.trim() || !firmAnswer.trim()) {
              onError("Strongest objection and firm answer are required.");
              return;
            }
            if (!calibReason.trim()) {
              onError("Calibration discount reason is required.");
              return;
            }
            const dc = Number(discounted);
            if (!Number.isFinite(dc) || dc < 0 || dc > 1) {
              onError("Discounted confidence must be a number between 0 and 1.");
              return;
            }
            onPublish({
              action: "publish",
              checklist: localCheck,
              evidenceSummary,
              exitConditions,
              strongestObjection: { objection, firmAnswer },
              openQuestionsAdjacent: openQs
                .split("\n")
                .map((s) => s.trim())
                .filter(Boolean),
              voiceComparisons,
              discountedConfidence: dc,
              statedConfidence: defaultStatedConfidence,
              calibrationDiscountReason: calibReason,
              slug: slug.trim() || undefined,
            });
          }}
        >
          Publish
        </button>
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            const ask = revisionAsk.trim();
            if (!ask) {
              onError("Revision ask is required.");
              return;
            }
            onNeedsRevision(ask);
          }}
        >
          Needs revision
        </button>
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            const reason = declineReason.trim();
            if (!reason) {
              onError("Decline reason is required.");
              return;
            }
            onDecline(reason);
          }}
        >
          Decline
        </button>
      </div>

      <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        Revision ask (required for “Needs revision”)
        <textarea
          value={revisionAsk}
          onChange={(e) => setRevisionAsk(e.target.value)}
          rows={2}
          style={{ width: "100%", background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
        />
      </label>

      <label style={{ color: "var(--parchment-dim)", fontSize: "0.8rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        Decline reason (required for “Decline”)
        <textarea
          value={declineReason}
          onChange={(e) => setDeclineReason(e.target.value)}
          rows={2}
          style={{ width: "100%", background: "var(--obsidian)", color: "var(--parchment)", padding: "0.5rem" }}
        />
      </label>

      <p style={{ fontSize: "0.75rem", color: "var(--parchment-dim)", margin: 0 }}>
        Review id: <code>{reviewId}</code>
      </p>
    </div>
  );
}
