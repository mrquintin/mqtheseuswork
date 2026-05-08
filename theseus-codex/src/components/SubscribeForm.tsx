"use client";

import { useState } from "react";

export type SubscribeFormScope =
  | { scope: "firm" }
  | { scope: "methodology"; scopeKey: string }
  | { scope: "domain"; scopeKey: string }
  | { scope: "conclusion"; scopeKey: string };

type SubscribeFormProps = {
  /** Scope this form will subscribe to. */
  target: SubscribeFormScope;
  /** Optional override of the heading/intro shown above the field. */
  title?: string;
  intro?: string;
  className?: string;
};

type SubmitState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; message: string }
  | { kind: "err"; message: string };

export default function SubscribeForm({
  target,
  title = "Follow this thread",
  intro,
  className,
}: SubscribeFormProps) {
  const [email, setEmail] = useState("");
  const [cadence, setCadence] = useState<"weekly" | "immediate" | "monthly">("weekly");
  const [state, setState] = useState<SubmitState>({ kind: "idle" });

  const scopeLabel = describe(target);
  const helper =
    intro ||
    `Get a digest when the firm publishes new material, revisions, or retractions for ${scopeLabel}. Double opt-in. One-click unsubscribe in every email. No tracking pixels.`;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (state.kind === "loading") return;
    setState({ kind: "loading" });
    try {
      const payload: Record<string, string> = {
        email: email.trim(),
        scope: target.scope,
        cadence,
      };
      if (target.scope !== "firm") {
        payload.scopeKey = target.scopeKey;
      }
      const res = await fetch("/api/public/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = (await res.json().catch(() => ({}))) as {
        message?: string;
        error?: string;
        status?: string;
      };
      if (!res.ok) {
        setState({ kind: "err", message: data.error || `Request failed (${res.status})` });
        return;
      }
      setState({
        kind: "ok",
        message:
          data.message ||
          (data.status === "active"
            ? "Already subscribed and confirmed."
            : "Check your inbox to confirm."),
      });
      setEmail("");
    } catch (err) {
      setState({ kind: "err", message: err instanceof Error ? err.message : "Network error" });
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className={className}
      data-testid="subscribe-form"
      data-scope={target.scope}
      data-scope-key={target.scope === "firm" ? "" : target.scopeKey}
      style={{
        border: "1px solid var(--stroke, rgba(232,225,211,0.18))",
        padding: "1rem 1.1rem",
        borderRadius: "4px",
      }}
    >
      <h3 style={{ margin: "0 0 0.4rem", fontSize: "0.95rem", letterSpacing: "0.04em" }}>
        {title}
      </h3>
      <p
        style={{
          color: "var(--parchment-dim, #999)",
          fontSize: "0.82rem",
          lineHeight: 1.45,
          margin: "0 0 0.8rem",
        }}
      >
        {helper}
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
        <label style={{ flex: "1 1 220px", minWidth: 0 }}>
          <span style={visuallyHidden}>Email</span>
          <input
            type="email"
            required
            autoComplete="email"
            placeholder="you@example.org"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={state.kind === "loading"}
            data-testid="subscribe-form-email"
            style={{
              width: "100%",
              padding: "0.5rem 0.6rem",
              fontFamily: "inherit",
              fontSize: "0.9rem",
              border: "1px solid var(--stroke, rgba(232,225,211,0.22))",
              background: "transparent",
              color: "inherit",
            }}
          />
        </label>
        <label style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
          <span style={visuallyHidden}>Cadence</span>
          <select
            value={cadence}
            onChange={(e) => setCadence(e.target.value as typeof cadence)}
            disabled={state.kind === "loading"}
            data-testid="subscribe-form-cadence"
            style={{
              padding: "0.45rem 0.5rem",
              fontFamily: "inherit",
              fontSize: "0.85rem",
              border: "1px solid var(--stroke, rgba(232,225,211,0.22))",
              background: "transparent",
              color: "inherit",
            }}
          >
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="immediate">Immediate (firm-wide major events)</option>
          </select>
        </label>
        <button
          type="submit"
          disabled={state.kind === "loading"}
          data-testid="subscribe-form-submit"
          style={{
            padding: "0.5rem 0.9rem",
            fontFamily: "inherit",
            fontSize: "0.78rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            border: "1px solid var(--amber, #d4a017)",
            background: "var(--amber, #d4a017)",
            color: "#120d08",
            cursor: state.kind === "loading" ? "wait" : "pointer",
          }}
        >
          {state.kind === "loading" ? "Sending…" : "Follow"}
        </button>
      </div>
      {state.kind === "ok" ? (
        <p
          role="status"
          data-testid="subscribe-form-ok"
          style={{ marginTop: "0.6rem", fontSize: "0.85rem", color: "var(--amber, #d4a017)" }}
        >
          {state.message}
        </p>
      ) : null}
      {state.kind === "err" ? (
        <p
          role="alert"
          data-testid="subscribe-form-err"
          style={{ marginTop: "0.6rem", fontSize: "0.85rem", color: "#c0392b" }}
        >
          {state.message}
        </p>
      ) : null}
    </form>
  );
}

const visuallyHidden: React.CSSProperties = {
  position: "absolute",
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: "hidden",
  clip: "rect(0,0,0,0)",
  border: 0,
};

function describe(target: SubscribeFormScope): string {
  switch (target.scope) {
    case "firm":
      return "the firm at large";
    case "methodology":
      return `the ${target.scopeKey} methodology`;
    case "domain":
      return `the ${target.scopeKey} domain`;
    case "conclusion":
      return "this conclusion";
  }
}
