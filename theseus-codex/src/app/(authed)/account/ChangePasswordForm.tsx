"use client";

import { useState } from "react";

/**
 * Passphrase rotation form. Three fields (current / new / confirm),
 * client-side parity check between the two new-password inputs before
 * we hit the API, server-side everything else. The form is friendly
 * about error messages — "Current passphrase is incorrect" is relayed
 * verbatim from the API, ditto for rate-limit messages.
 *
 * On success: clears all three inputs, shows a green confirmation
 * banner with a "you're still signed in here, but other devices need
 * to sign in again" note. The current cookie is rotated server-side
 * so we don't need to redirect.
 */
export default function ChangePasswordForm() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [state, setState] = useState<"idle" | "submitting" | "ok" | "error">(
    "idle",
  );
  const [message, setMessage] = useState("");

  const passwordsMatch = newPassword === confirmPassword;
  const newIsLongEnough = newPassword.length >= 8;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMessage("");
    if (!currentPassword) {
      setState("error");
      setMessage("Enter your current passphrase.");
      return;
    }
    if (!newIsLongEnough) {
      setState("error");
      setMessage("New passphrase must be at least 8 characters.");
      return;
    }
    if (!passwordsMatch) {
      setState("error");
      setMessage("New passphrase and confirmation don't match.");
      return;
    }
    if (currentPassword === newPassword) {
      setState("error");
      setMessage("New passphrase must differ from the current one.");
      return;
    }

    setState("submitting");
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ currentPassword, newPassword }),
      });
      const data = (await res.json()) as { ok?: boolean; error?: string };
      if (!res.ok || !data.ok) {
        setState("error");
        setMessage(data.error || `HTTP ${res.status}`);
        return;
      }
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setState("ok");
      setMessage(
        "Passphrase updated. You stay signed in here; every other device " +
          "is now signed out and will need to sign in again with the new one.",
      );
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="ascii-frame"
      data-label="PASSPHRASE"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        padding: "1.25rem 1.5rem",
        maxWidth: "480px",
      }}
    >
      <Labelled label="Current passphrase">
        <input
          type="password"
          autoComplete="current-password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          disabled={state === "submitting"}
          required
        />
      </Labelled>

      <Labelled
        label="New passphrase"
        hint="At least 8 characters. A short phrase is fine; length matters more than symbols."
      >
        <input
          type="password"
          autoComplete="new-password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          disabled={state === "submitting"}
          required
          minLength={8}
        />
      </Labelled>

      <Labelled
        label="Confirm new passphrase"
        hint={
          confirmPassword && !passwordsMatch
            ? "These don't match yet."
            : undefined
        }
      >
        <input
          type="password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          disabled={state === "submitting"}
          required
          style={
            confirmPassword && !passwordsMatch
              ? { borderColor: "var(--ember)" }
              : undefined
          }
        />
      </Labelled>

      {message && (
        <p
          style={{
            margin: 0,
            fontSize: "0.85rem",
            lineHeight: 1.5,
            color:
              state === "ok"
                ? "var(--success, #4ade80)"
                : state === "error"
                  ? "var(--ember)"
                  : "var(--parchment-dim)",
          }}
        >
          {message}
        </p>
      )}

      <button
        type="submit"
        className="btn-solid btn"
        disabled={
          state === "submitting" ||
          !currentPassword ||
          !newIsLongEnough ||
          !passwordsMatch
        }
        style={{ alignSelf: "flex-start" }}
      >
        {state === "submitting" ? "Updating…" : "Update passphrase"}
      </button>
    </form>
  );
}

function Labelled({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.35rem",
      }}
    >
      <span
        className="mono"
        style={{
          fontSize: "0.65rem",
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          color: "var(--amber-dim)",
        }}
      >
        {label}
      </span>
      {children}
      {hint ? (
        <span
          style={{
            fontSize: "0.75rem",
            color: "var(--parchment-dim)",
            lineHeight: 1.45,
          }}
        >
          {hint}
        </span>
      ) : null}
    </label>
  );
}
