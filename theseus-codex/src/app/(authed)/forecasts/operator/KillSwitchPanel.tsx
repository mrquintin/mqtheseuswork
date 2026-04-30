"use client";

import { Power, ShieldAlert } from "lucide-react";
import { useState } from "react";

import type { OperatorKillSwitchState } from "@/lib/forecastsTypes";

export async function postKillSwitchEngage(reason: string, note?: string): Promise<OperatorKillSwitchState> {
  const res = await fetch("/api/forecasts/operator/kill-switch/engage", {
    body: JSON.stringify({ note: note || null, reason }),
    headers: { "content-type": "application/json" },
    method: "POST",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `engage failed with ${res.status}`);
  }
  return res.json() as Promise<OperatorKillSwitchState>;
}

export async function postKillSwitchDisengage(note: string): Promise<OperatorKillSwitchState> {
  const res = await fetch("/api/forecasts/operator/kill-switch/disengage", {
    body: JSON.stringify({ note }),
    headers: { "content-type": "application/json" },
    method: "POST",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `disengage failed with ${res.status}`);
  }
  return res.json() as Promise<OperatorKillSwitchState>;
}

export default function KillSwitchPanel({
  initialState,
}: {
  initialState: OperatorKillSwitchState;
}) {
  const [state, setState] = useState(initialState);
  const [reason, setReason] = useState(initialState.kill_switch_reason || "OPERATOR");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const engaged = state.kill_switch_engaged;
  const canSubmit = engaged ? note.trim().length >= 20 : reason.trim().length > 0;

  return (
    <section
      className="portal-card"
      data-kill-switch-state={engaged ? "engaged" : "clear"}
      style={{
        borderColor: engaged ? "rgba(185, 92, 92, 0.65)" : "rgba(205, 151, 67, 0.55)",
        padding: "1rem",
      }}
    >
      <h2 style={{ color: engaged ? "var(--ember)" : "var(--amber)", fontFamily: "'Cinzel', serif", margin: 0 }}>
        Kill switch
      </h2>
      <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem", margin: "0.25rem 0 0" }}>
        {engaged ? `ENGAGED: ${state.kill_switch_reason || "reason unavailable"}` : "Live order submission is allowed if all other gates pass."}
      </p>

      <label style={{ color: "var(--parchment)", display: "grid", gap: "0.35rem", marginTop: "0.9rem" }}>
        <span className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.62rem", textTransform: "uppercase" }}>
          {engaged ? "Disengagement note" : "Engagement reason"}
        </span>
        {engaged ? (
          <textarea
            minLength={20}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Required: at least 20 characters."
            rows={4}
            style={{ background: "rgba(0,0,0,0.2)", color: "var(--parchment)", padding: "0.65rem" }}
            value={note}
          />
        ) : (
          <input
            onChange={(event) => setReason(event.target.value)}
            style={{ background: "rgba(0,0,0,0.2)", color: "var(--parchment)", padding: "0.65rem" }}
            value={reason}
          />
        )}
      </label>

      {error ? <p role="alert" style={{ color: "var(--ember)" }}>{error}</p> : null}

      <button
        className="btn"
        disabled={!canSubmit || busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const next = engaged ? await postKillSwitchDisengage(note) : await postKillSwitchEngage(reason);
            setState(next);
            setNote("");
          } catch (err) {
            setError(err instanceof Error ? err.message : "Kill-switch update failed");
          } finally {
            setBusy(false);
          }
        }}
        style={{
          background: engaged ? "rgba(126, 166, 133, 0.12)" : "rgba(205, 151, 67, 0.16)",
          borderColor: engaged ? "rgba(126, 166, 133, 0.6)" : "rgba(205, 151, 67, 0.75)",
          color: engaged ? "rgba(184, 231, 192, 0.95)" : "var(--amber)",
          marginTop: "0.9rem",
        }}
        type="button"
      >
        {engaged ? <Power aria-hidden="true" size={16} /> : <ShieldAlert aria-hidden="true" size={16} />}{" "}
        {busy ? "Updating..." : engaged ? "Disengage kill switch" : "Engage kill switch"}
      </button>
    </section>
  );
}
