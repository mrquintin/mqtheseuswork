"use client";

import { Suspense, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";

import LabyrinthIcon from "./LabyrinthIcon";

// The ASCII hero is a heavy client component (does its own 3D projection
// every frame). Import it dynamically with SSR off so it doesn't attempt
// to reach for `document` during the server render — and so the static
// SSR payload stays small for the Gate.
const AsciiHero = dynamic(() => import("./AsciiHero"), {
  ssr: false,
  loading: () => (
    <div style={{ height: 360, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <LabyrinthIcon size={160} glow />
    </div>
  ),
});

/**
 * The Gate.
 *
 * Lives at `/login`. The Codex's front door is the public blog at `/`;
 * founders authenticate through this component and are dropped into
 * `/dashboard` (or `?next=…` if middleware bounced them off a
 * protected route).
 *
 * Three authentication phases (state machine):
 *
 *   idle       — normal form, labyrinth rotates slowly, cursor blinks.
 *   submitting — input disabled, button shows "opening…", labyrinth glows
 *                brighter but nothing else moves. Transition is reversible:
 *                on auth failure we return to idle and surface the error.
 *   entering   — auth succeeded. The form + wordmark + labyrinth gently
 *                fade out and drift down a hair while a single thin amber
 *                hairline sweeps across the horizon. ~700ms, no flash, no
 *                scale explosion — just a quiet, precise threshold crossing.
 *                Reduced-motion mode skips to a flat 200ms fade.
 *
 * Prior revisions of this file included a three-layer "ignition" — a
 * rotating sunburst, a radial amber shockwave that filled the viewport in
 * solid amber, and the labyrinth scaling past 9×. It was loud and the
 * amber flash was the most frequent user complaint. Replaced with the
 * horizon-hairline sweep below; the arrival half (`EntranceWelcome`)
 * mirrors it on the dashboard side.
 */

type Phase = "idle" | "submitting" | "entering";
/**
 * The Gate has two modes:
 *
 *   "login"  — the classic sign-in form. Default.
 *   "rotate" — unauthenticated password rotation. Lets a founder
 *              change their passphrase without being logged in first
 *              (useful when they've stopped trusting their current
 *              passphrase for any reason — leaked, shared, or just
 *              time for a refresh). On success the server rotates
 *              the hash AND mints a session with the new passphrase,
 *              so the same "entering → /dashboard" ignition ritual
 *              plays immediately afterwards. No admin involvement.
 *
 * Both modes share the entering/submitting phase machine and the
 * same post-auth navigation path so the success flow feels
 * identical.
 */
type Mode = "login" | "rotate";

function GateInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("theseus-local");
  // Rotate-mode-only fields. Kept in state even when mode="login"
  // so toggling back and forth doesn't drop user input mid-flight.
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");

  function toggleMode() {
    if (phase !== "idle") return;
    setError("");
    setMode((m) => (m === "login" ? "rotate" : "login"));
  }

  /**
   * Shared post-success choreography: play the ignition animation
   * for ~720ms, then push to the resolved next URL. Used by BOTH
   * the login submit and the rotate submit so the two paths share
   * the same cinematic arrival.
   */
  function enterCodex() {
    setPhase("entering");
    try {
      window.sessionStorage.setItem("codex:just-entered", "1");
    } catch {
      /* private-mode / disabled storage is non-fatal. */
    }
    const holdMs =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? 200
        : 720;
    window.setTimeout(() => {
      const next = searchParams.get("next") || "/dashboard";
      router.push(next.startsWith("/") ? next : "/dashboard");
      router.refresh();
    }, holdMs);
  }

  async function handleLoginSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setPhase("submitting");

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, organizationSlug }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.error || "Login failed");
        setPhase("idle");
        return;
      }

      enterCodex();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
      setPhase("idle");
    }
  }

  async function handleRotateSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    // Client-side mirrors of the server's rules so the user gets
    // instant feedback without a round-trip. Server re-validates.
    if (newPassword.length < 8) {
      setError("New passphrase must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New passphrase and confirmation don't match.");
      return;
    }
    if (newPassword === password) {
      setError("New passphrase must differ from the current one.");
      return;
    }
    setPhase("submitting");

    try {
      const res = await fetch("/api/auth/rotate-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          organizationSlug,
          currentPassword: password,
          newPassword,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.error || "Passphrase rotation failed");
        setPhase("idle");
        return;
      }

      // The rotate-password route mints a session on success, so the
      // caller is logged in with the new credential — we can play the
      // same ignition animation and drop them into /dashboard.
      enterCodex();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
      setPhase("idle");
    }
  }

  const isLocked = phase !== "idle";

  return (
    <main
      style={{
        position: "relative",
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "3rem 1.5rem",
        overflow: "hidden",
      }}
    >
      {/* Single visual effect during `entering`: a thin amber hairline
          strokes horizontally across the vertical midline of the viewport.
          It starts at 0px wide from the centre point and grows outward to
          the viewport edges, then dims. No flash, no fills, no bombast —
          just a precise threshold indicator. See `.gate-hairline` keyframes
          in globals.css.

          We use a wrapper with `inset: 0, display: grid, place-items: center`
          so the line is always centred regardless of the form's scroll
          position on short viewports. */}
      {phase === "entering" ? (
        <div
          aria-hidden="true"
          style={{
            position: "fixed",
            inset: 0,
            display: "grid",
            placeItems: "center",
            pointerEvents: "none",
            zIndex: 9000,
          }}
        >
          <div className="gate-hairline" />
        </div>
      ) : null}

      {/* The hero (rotating labyrinth + colonnade in amber ASCII). On
          `entering` it participates in the same gentle fade-down as the
          form below — no scale explosion, no rotation spike. */}
      <div
        className={phase === "entering" ? "gate-leave" : "gate-pulse"}
        style={{
          position: "relative",
          marginBottom: "1.5rem",
          filter:
            phase === "submitting"
              ? "drop-shadow(0 0 24px var(--amber-glow)) drop-shadow(0 0 8px var(--amber))"
              : "drop-shadow(0 0 12px var(--amber-glow))",
          transition: "filter 0.35s ease",
        }}
      >
        <AsciiHero cols={66} rows={28} size={560} />
      </div>

      {/* Wordmark + Latin tag. On `entering` these fade out and drift
          down a hair along with the form — a single unified exit. */}
      <div
        className={phase === "entering" ? "gate-leave" : undefined}
        style={{
          textAlign: "center",
        }}
      >
        <h1
          style={{
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            fontSize: "clamp(2.5rem, 7vw, 4.5rem)",
            letterSpacing: "0.24em",
            color: "var(--amber)",
            textShadow: "var(--glow-lg)",
            margin: 0,
            fontWeight: 700,
          }}
        >
          THESEUS
        </h1>
        <p
          className="mono"
          style={{
            fontSize: "0.78rem",
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginTop: "0.5rem",
            marginBottom: "0.25rem",
          }}
        >
          Codex
        </p>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "1.05rem",
            color: "var(--parchment-dim)",
            marginTop: "0.25rem",
            marginBottom: "2.25rem",
          }}
        >
          In consilio lucem. <span style={{ opacity: 0.6 }}>·</span> Light in the deliberation.
        </p>
      </div>

      {/* The form. Hidden on `entering`; pointer-events off on `submitting`
          so the user can't double-fire the request. The ascii-frame class
          gives it the labeled bordered look that matches the Dashboard
          sections so the gate feels like part of the same vocabulary.

          Two modes share the same frame — the toggle at the bottom
          flips between login and passphrase-rotation. Rotation needs
          two extra fields (new passphrase + confirmation) and swaps
          the action, but every other affordance (organization, email,
          current passphrase, submit button, error line) stays the same
          between modes so there's no visual discontinuity. */}
      <form
        onSubmit={mode === "login" ? handleLoginSubmit : handleRotateSubmit}
        aria-label={
          mode === "login"
            ? "Sign in to the Theseus Codex"
            : "Rotate passphrase from the Theseus Codex gate"
        }
        className={`ascii-frame${phase === "entering" ? " gate-leave" : ""}`}
        data-label={
          mode === "login"
            ? "INTROITUS · ENTER"
            : "CLAVIS · ROTATE PASSPHRASE"
        }
        style={{
          width: "min(420px, 100%)",
          display: "flex",
          flexDirection: "column",
          gap: "0.9rem",
          pointerEvents: isLocked ? "none" : "auto",
        }}
      >
        <FormField
          label="Organization"
          hint={
            <>
              Multi-tenant slug. Local seed defaults to{" "}
              <code className="mono">theseus-local</code>.
            </>
          }
        >
          <input
            type="text"
            value={organizationSlug}
            onChange={(e) => setOrganizationSlug(e.target.value)}
            placeholder="theseus-local"
            autoComplete="organization"
            disabled={isLocked}
          />
        </FormField>

        <FormField label="Email">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
            disabled={isLocked}
          />
        </FormField>

        <FormField
          label={mode === "login" ? "Passphrase" : "Current passphrase"}
        >
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="current-password"
            required
            disabled={isLocked}
          />
        </FormField>

        {mode === "rotate" ? (
          <>
            <FormField
              label="New passphrase"
              hint={<>At least 8 characters. Must differ from current.</>}
            >
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="new-password"
                minLength={8}
                required
                disabled={isLocked}
              />
            </FormField>

            <FormField label="Confirm new passphrase">
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="new-password"
                minLength={8}
                required
                disabled={isLocked}
              />
            </FormField>
          </>
        ) : null}

        {error ? (
          <p
            role="alert"
            className="mono"
            style={{
              color: "var(--ember)",
              fontSize: "0.78rem",
              letterSpacing: "0.06em",
              margin: "0.25rem 0 -0.25rem",
            }}
          >
            [auth denied] {error}
          </p>
        ) : null}

        <button
          type="submit"
          className="btn-solid btn"
          disabled={isLocked}
          style={{
            marginTop: "0.5rem",
            width: "100%",
            opacity: isLocked ? 0.75 : 1,
            position: "relative",
          }}
        >
          {phase === "idle" &&
            (mode === "login"
              ? "Enter the Codex"
              : "Rotate passphrase & enter")}
          {phase === "submitting" &&
            (mode === "login"
              ? "Opening the gate…"
              : "Rotating passphrase…")}
          {phase === "entering" && "Crossing the threshold…"}
        </button>

        {/* Mode toggle. A single text button swaps the form between
            login and rotation. Disabled while the form is mid-flight
            so the user can't change modes after submit. */}
        <button
          type="button"
          onClick={toggleMode}
          disabled={isLocked}
          className="mono"
          style={{
            background: "none",
            border: "none",
            color: "var(--amber-dim)",
            cursor: isLocked ? "not-allowed" : "pointer",
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            textAlign: "center",
            padding: "0.25rem",
            marginTop: "0.1rem",
            opacity: isLocked ? 0.55 : 1,
          }}
        >
          {mode === "login"
            ? "Change passphrase instead →"
            : "← Back to sign in"}
        </button>

        <p
          className="mono"
          style={{
            textAlign: "center",
            marginTop: "0.25rem",
            fontSize: "0.7rem",
            letterSpacing: "0.1em",
            color: "var(--parchment-dim)",
          }}
        >
          {mode === "login"
            ? "Contact an admin for credentials."
            : "Rotation needs your current passphrase; if you've lost it, an admin must reset the account."}
        </p>
      </form>
    </main>
  );
}

/** Small helper for a labeled input row, so the form layout stays consistent
 *  and the uppercase-letterspaced label styling isn't copy-pasted 3 times. */
function FormField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        className="mono"
        style={{
          fontSize: "0.65rem",
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          color: "var(--amber-dim)",
          display: "block",
          marginBottom: "0.35rem",
        }}
      >
        {label}
      </label>
      {children}
      {hint ? (
        <p
          style={{
            fontSize: "0.7rem",
            color: "var(--parchment-dim)",
            marginTop: "0.25rem",
            marginBottom: 0,
            lineHeight: 1.45,
          }}
        >
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export default function Gate() {
  return (
    <Suspense
      fallback={
        <main style={{ padding: "4rem", textAlign: "center" }}>
          <div className="mono" style={{ color: "var(--amber-dim)" }}>
            Warming phosphor…
          </div>
        </main>
      }
    >
      <GateInner />
    </Suspense>
  );
}
