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

function GateInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("theseus-local");
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");

  async function handleSubmit(e: React.FormEvent) {
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

      // Auth succeeded. Play the ignition animation before navigating so
      // the user arrives inside the Codex rather than cutting to it. The
      // dashboard side reads the session flag on first mount and plays
      // the arrival half of the animation (fade-in from amber + Latin
      // welcome tag) — see EntranceWelcome in the (authed) layout.
      setPhase("entering");
      try {
        // sessionStorage is fine: it survives the navigation but is
        // scoped to this tab, so a subsequent manual refresh doesn't
        // replay the animation.
        window.sessionStorage.setItem("codex:just-entered", "1");
      } catch {
        /* private-mode / disabled storage is non-fatal; arrival just won't animate. */
      }

      // Match the CSS keyframe duration. The gate-leave animation
      // (hairline sweep + fade-down) runs ~700ms; hold a hair past
      // that so the sweep completes before the navigation resolves.
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
          sections so the gate feels like part of the same vocabulary. */}
      <form
        onSubmit={handleSubmit}
        aria-label="Sign in to the Theseus Codex"
        className={`ascii-frame${phase === "entering" ? " gate-leave" : ""}`}
        data-label="INTROITUS · ENTER"
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

        <FormField label="Passphrase">
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
          {phase === "idle" && "Enter the Codex"}
          {phase === "submitting" && "Opening the gate…"}
          {phase === "entering" && "Crossing the threshold…"}
        </button>

        <p
          className="mono"
          style={{
            textAlign: "center",
            marginTop: "0.5rem",
            fontSize: "0.7rem",
            letterSpacing: "0.1em",
            color: "var(--parchment-dim)",
          }}
        >
          Contact an admin for credentials.
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
