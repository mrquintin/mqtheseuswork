import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import MethodTabs from "@/components/MethodTabs";
import PublicHeader from "@/components/PublicHeader";
import SubscribeForm from "@/components/SubscribeForm";
import { getCatalog, publicModesForMethod } from "@/lib/failureModes";
import { getFounder } from "@/lib/auth";
import {
  driftColor,
  driftLabel,
  methodEntry,
} from "@/lib/methodologyManifest";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ method: string }>;
}): Promise<Metadata> {
  const { method } = await params;
  const methodName = decodeURIComponent(method);
  const entry = await methodEntry(methodName);

  // OG card text: a one-liner an outside reader can scan in a feed.
  // Slope + domain + drift is the firm's most informative summary.
  const slope = entry?.calibration?.slope;
  const domain = entry?.calibration?.domain || entry?.domain || "—";
  const slopeFragment =
    typeof slope === "number"
      ? `slope ${slope.toFixed(2)}`
      : "calibration pending";
  const driftFragment = entry?.drift.state
    ? entry.drift.state === "ok"
      ? ""
      : ` · drift ${driftLabel(entry.drift.state).toLowerCase()}`
    : "";
  const summary = entry
    ? `${entry.description}`
    : `Methodology page for ${methodName}.`;
  const ogTitle = `${methodName} · ${slopeFragment} · ${domain}${driftFragment}`;

  return {
    title: `Methodology · ${methodName}`,
    description: summary,
    openGraph: {
      title: ogTitle,
      description: summary,
      type: "article",
      url: `/methodology/${encodeURIComponent(methodName)}`,
    },
    twitter: {
      card: "summary",
      title: ogTitle,
      description: summary,
    },
  };
}

/**
 * Method overview tab — the default landing for `/methodology/[method]`.
 * Failure-mode listing has moved to the dedicated `/failures` sub-route
 * so it is independently shareable; this page summarizes and links.
 */
export default async function PublicMethodologyMethodPage({
  params,
}: {
  params: Promise<{ method: string }>;
}) {
  const { method } = await params;
  const methodName = decodeURIComponent(method);
  const catalog = getCatalog(methodName);
  if (!catalog) notFound();

  const publicModes = publicModesForMethod(methodName);
  const founder = await getFounder();
  const entry = await methodEntry(methodName);

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container public-methodology-page">
        <Link
          href="/methodology"
          className="public-muted"
          style={{ fontSize: "0.75rem" }}
        >
          ← Methodology
        </Link>
        <h1 className="public-title" style={{ marginTop: "0.5rem" }}>
          <span style={{ fontFamily: "monospace" }}>{methodName}</span>
        </h1>
        <p className="public-muted" style={{ marginTop: "-0.4rem", fontSize: "0.85rem" }}>
          v{entry?.version ?? "—"} · {catalog.method}
        </p>

        <MethodTabs method={methodName} active="overview" />

        <section className="public-section">
          <h2>Overview</h2>
          <p>
            {entry?.description ||
              "This method is part of Theseus's published methodology."}
          </p>
        </section>

        <section className="public-section" aria-label="At-a-glance metrics">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
              gap: "0.75rem",
            }}
          >
            <Stat
              label="Conclusions produced"
              value={String(entry?.conclusionsProduced ?? 0)}
            />
            <Stat
              label="Calibration slope"
              value={
                entry?.calibration
                  ? entry.calibration.slope.toFixed(2)
                  : "—"
              }
              hint={
                entry?.calibration
                  ? `n=${entry.calibration.sampleSize}${
                      entry.calibration.domain ? ` · ${entry.calibration.domain}` : ""
                    }`
                  : "below publish gate"
              }
            />
            <Stat
              label="Drift status"
              value={entry ? driftLabel(entry.drift.state) : "—"}
              color={entry ? driftColor(entry.drift.state) : undefined}
            />
            <Stat
              label="Public failure modes"
              value={String(publicModes.length)}
              hint={
                catalog.failures === "deliberately-empty"
                  ? "deliberately empty"
                  : undefined
              }
            />
            <Stat
              label="Last review"
              value={
                entry?.lastReviewDate
                  ? entry.lastReviewDate.slice(0, 10)
                  : "—"
              }
            />
          </div>
        </section>

        {entry?.drift.state && entry.drift.state !== "ok" ? (
          <section className="public-section">
            <div
              className="public-card"
              role="note"
              style={{
                padding: "0.85rem 1.1rem",
                borderLeft: `3px solid ${driftColor(entry.drift.state)}`,
              }}
            >
              <h3 style={{ margin: 0, fontSize: "0.95rem" }}>
                Drift alert active
              </h3>
              <p
                className="public-muted"
                style={{ margin: "0.4rem 0 0", fontSize: "0.85rem" }}
              >
                The firm flags this method as currently drifting from its
                own historical baseline. Most recent alert observed{" "}
                {entry.drift.lastActiveAt
                  ? entry.drift.lastActiveAt.slice(0, 10)
                  : "recently"}
                . Diagnostic numbers are kept internal; what is public is
                the fact that the firm watches its methods and says so when
                one stops behaving.
              </p>
            </div>
          </section>
        ) : null}

        <section className="public-section">
          <h2>What is on the other tabs</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            <NextTab
              href={`/methodology/${encodeURIComponent(methodName)}/track-record`}
              label="Track record"
              body="Calibration slope, weighted Brier, severity-pass rate, with a 90% bootstrap confidence band. Only published once the sample clears the publish gate."
            />
            <NextTab
              href={`/methodology/${encodeURIComponent(methodName)}/domain`}
              label="Domain"
              body="Where the method is judged in-bounds, edge-case, or out-of-bounds, based on the recorded domain bound verdicts."
            />
            <NextTab
              href={`/methodology/composition#${encodeURIComponent(methodName)}`}
              label="Composition"
              body="Where this method sits in the public-visible dependency graph — what it composes, what composes it."
            />
            <NextTab
              href={`/methodology/${encodeURIComponent(methodName)}/failures`}
              label="Failure modes"
              body={`${publicModes.length} of ${
                catalog.failures === "deliberately-empty" ? 0 : catalog.modes.length
              } modes published. Triggers, worked examples, mitigations, and citations.`}
            />
            <NextTab
              href={`/c?method=${encodeURIComponent(methodName)}`}
              label="Conclusions produced"
              body={`Public conclusions linked to this method. Currently ${
                entry?.conclusionsProduced ?? 0
              } published.`}
            />
          </ul>
        </section>

        <section className="public-section" aria-label="Follow this methodology">
          <SubscribeForm
            target={{ scope: "methodology", scopeKey: methodName }}
            title={`Follow ${methodName}`}
            intro={`Receive a digest when the firm publishes new work, revisions, or retractions tied to the ${methodName} method, plus calibration breaches that change how it is judged. Double opt-in. One-click unsubscribe in every email. No tracking pixels.`}
          />
        </section>
      </main>
    </>
  );
}

function Stat({
  label,
  value,
  hint,
  color,
}: {
  label: string;
  value: string;
  hint?: string;
  color?: string;
}) {
  return (
    <div
      className="public-card"
      style={{ padding: "0.75rem 0.9rem" }}
    >
      <div
        className="mono public-muted"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          marginBottom: "0.4rem",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: "1.2rem",
          fontWeight: 600,
          color,
        }}
      >
        {value}
      </div>
      {hint ? (
        <div
          className="public-muted"
          style={{ fontSize: "0.72rem", marginTop: "0.3rem" }}
        >
          {hint}
        </div>
      ) : null}
    </div>
  );
}

function NextTab({
  href,
  label,
  body,
}: {
  href: string;
  label: string;
  body: string;
}) {
  return (
    <li style={{ margin: "0.6rem 0" }}>
      <Link
        href={href}
        className="public-card public-method-card"
        style={{
          display: "block",
          textDecoration: "none",
          color: "inherit",
          padding: "0.85rem 1rem",
        }}
      >
        <div
          className="mono"
          style={{
            fontSize: "0.62rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--amber, #d4a017)",
            marginBottom: "0.3rem",
          }}
        >
          {label} →
        </div>
        <div style={{ fontSize: "0.9rem" }}>{body}</div>
      </Link>
    </li>
  );
}

