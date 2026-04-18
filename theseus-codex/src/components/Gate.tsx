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
 * The Codex has no public face — `/` renders this component when there is
 * no session, and redirects to `/dashboard` when there is one. The gate is
 * therefore what every first-time visitor sees, and it has exactly one
 * thing to do: get the founder into the system, dramatically.
 *
 * The drama is not a gimmick; it announces the character of the instrument.
 * The slow rotation of the labyrinth, the phosphor glow, the Latin tag, the
 * amber flash on authentication — these are the aesthetic commitments that
 * will reappear throughout the app. A new founder who enters this way knows
 * they are not using a generic dashboard; they are stepping into a specific
 * institution with a specific voice.
 *
 * Three authentication phases (state machine):
 *
 *   idle       — normal form, labyrinth rotates slowly, cursor blinks.
 *   submitting — input disabled, button shows "opening…", labyrinth glows
 *                brighter but nothing else moves. Transition is reversible:
 *                on auth failure we return to idle and surface the error.
 *   entering   — auth succeeded. The form fades out, the labyrinth scales
 *                up and spins toward the viewer, an amber flash crossfades
 *                the screen to solid amber, and then we navigate. Total
 *                duration ~1.4s. Runs in reduced-motion mode as a simple
 *                250ms fade.
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

      // Match the CSS keyframe durations. The longest is `gate-shockwave`
      // at 1.3s. We hold a hair past that so the amber flash fully covers
      // the old DOM before the next page paints — otherwise you get a
      // brief "peek" of the gate behind the transition.
      const holdMs =
        typeof window !== "undefined" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? 180
          : 1380;

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
      {/* Ignition layer 1 — sunburst rays. Sits BELOW the amber flash so
          the rays read as "light escaping the threshold" while the flash
          above them brightens. Only mounts in the `entering` phase so
          idle paints don't carry this div at all (conic-gradient can be
          expensive to rasterise on some GPUs; unmounting is free). */}
      {phase === "entering" ? <div aria-hidden="true" className="gate-rays" /> : null}

      {/* Ignition layer 2 — the amber shockwave. Idle = invisible; entering
          = animated radial gradient that expands from the viewport centre
          outward and fills the screen. Separate fixed div so it composites
          above the labyrinth + form but below the rays mix-blend. */}
      <div
        aria-hidden="true"
        className={phase === "entering" ? "gate-flash" : undefined}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 9000,
          pointerEvents: "none",
          background: "transparent",
          opacity: 0,
        }}
      />

      {/* The hero is a rotating 3D wireframe (labyrinth + colonnade) that
          is rendered live and then converted to amber ASCII art — so the
          first thing a visitor sees is a real 3D scene projected through
          the shape-vector ASCII engine, not a static SVG.
          On `entering` we scale + fade the whole ASCII block to suggest
          "falling through the labyrinth". */}
      <div
        className={phase === "entering" ? "gate-open" : "gate-pulse"}
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

      {/* Wordmark + Latin tag. On `entering` these fade to zero opacity so
          only the labyrinth is visible at the moment of transition. */}
      <div
        style={{
          opacity: phase === "entering" ? 0 : 1,
          transition: "opacity 0.35s ease",
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
        className="ascii-frame"
        data-label="INTROITUS · ENTER"
        style={{
          width: "min(420px, 100%)",
          display: "flex",
          flexDirection: "column",
          gap: "0.9rem",
          opacity: phase === "entering" ? 0 : 1,
          transform: phase === "entering" ? "translateY(12px)" : "translateY(0)",
          transition: "opacity 0.45s ease, transform 0.45s ease",
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
