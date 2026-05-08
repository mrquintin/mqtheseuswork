import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import MethodTabs from "@/components/MethodTabs";
import PublicHeader from "@/components/PublicHeader";
import { getCatalog, publicModesForMethod } from "@/lib/failureModes";
import { getFounder } from "@/lib/auth";
import {
  driftColor,
  driftLabel,
  methodEntry,
} from "@/lib/methodologyManifest";

const METHOD_NAME = "contradiction_geometry";
const ABLATION_PDF_HREF = "/research/Householder_Ablation.pdf";

export const metadata: Metadata = {
  title: "Methodology · contradiction_geometry",
  description:
    "Contradiction-geometry method overview, including the Householder reflection ablation the firm published against itself.",
};

export default async function ContradictionGeometryMethodPage() {
  const catalog = getCatalog(METHOD_NAME);
  if (!catalog) notFound();

  const publicModes = publicModesForMethod(METHOD_NAME);
  const founder = await getFounder();
  const entry = await methodEntry(METHOD_NAME);

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
          <span style={{ fontFamily: "monospace" }}>{METHOD_NAME}</span>
        </h1>
        <p
          className="public-muted"
          style={{ marginTop: "-0.4rem", fontSize: "0.85rem" }}
        >
          v{entry?.version ?? "—"} · {catalog.method}
        </p>

        <MethodTabs method={METHOD_NAME} active="overview" />

        <section className="public-section">
          <h2>Overview</h2>
          <p>
            {entry?.description ||
              "Detects contradiction via Hoyer sparsity of embedding difference vectors, optionally composed with a learned reflection direction estimated from contradicting exemplar pairs."}
          </p>
        </section>

        <section className="public-section">
          <h2>What we tested</h2>
          <p>
            The reflection step in the contradiction-geometry pipeline is the
            firm's most distinctive claim — that contradicting claims live in
            a learned reflection direction in embedding space. It is also the
            step most likely to be inherited from an earlier prototype rather
            than carrying its own weight. The firm ran an ablation study to
            answer that question honestly, against the same frozen QH-v1
            benchmark the public leaderboard runs on.
          </p>
          <p>
            Five variants were compared: the production pipeline (control),
            the same pipeline with the reflection skipped, the same pipeline
            with the learned direction replaced by a random unit vector,
            an asymmetric variant that reflects only the antagonistic half
            (cosine &lt; 0), and a variant that scores the reflected raw
            embedding rather than the difference vector. Per-item
            correctness was compared via paired McNemar with effect-size
            and Wilson confidence bands; the report does not pre-commit to a
            decision, it surfaces what the numbers say.
          </p>
          <p>
            <a
              href={ABLATION_PDF_HREF}
              className="public-muted"
              style={{ fontFamily: "monospace", fontSize: "0.85rem" }}
            >
              Householder_Ablation.pdf
            </a>
          </p>
          <p
            className="public-muted"
            style={{ fontSize: "0.78rem", marginTop: "0.4rem" }}
          >
            Numbers in the PDF are regenerated from{" "}
            <span style={{ fontFamily: "monospace" }}>
              ablation_results.json
            </span>{" "}
            on every run; no number is hand-edited. If the no-reflection
            variant is statistically indistinguishable from the control
            here and on the firm's internal eval, the firm faces a
            documented choice: keep the step on principled grounds with a
            new RATIONALE entry, or remove it in a follow-up prompt with
            a full review trail. This research output is not a refactor.
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
                entry?.calibration ? entry.calibration.slope.toFixed(2) : "—"
              }
              hint={
                entry?.calibration
                  ? `n=${entry.calibration.sampleSize}${
                      entry.calibration.domain
                        ? ` · ${entry.calibration.domain}`
                        : ""
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
                entry?.lastReviewDate ? entry.lastReviewDate.slice(0, 10) : "—"
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
                The firm flags this method as currently drifting from its own
                historical baseline. Most recent alert observed{" "}
                {entry.drift.lastActiveAt
                  ? entry.drift.lastActiveAt.slice(0, 10)
                  : "recently"}
                . Diagnostic numbers are kept internal; what is public is the
                fact that the firm watches its methods and says so when one
                stops behaving.
              </p>
            </div>
          </section>
        ) : null}

        <section className="public-section">
          <h2>What is on the other tabs</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            <NextTab
              href={`/methodology/${encodeURIComponent(METHOD_NAME)}/track-record`}
              label="Track record"
              body="Calibration slope, weighted Brier, severity-pass rate, with a 90% bootstrap confidence band. Only published once the sample clears the publish gate."
            />
            <NextTab
              href={`/methodology/${encodeURIComponent(METHOD_NAME)}/domain`}
              label="Domain"
              body="Where the method is judged in-bounds, edge-case, or out-of-bounds, based on the recorded domain bound verdicts."
            />
            <NextTab
              href={`/methodology/composition#${encodeURIComponent(METHOD_NAME)}`}
              label="Composition"
              body="Where this method sits in the public-visible dependency graph — what it composes, what composes it."
            />
            <NextTab
              href={`/methodology/${encodeURIComponent(METHOD_NAME)}/failures`}
              label="Failure modes"
              body={`${publicModes.length} of ${
                catalog.failures === "deliberately-empty"
                  ? 0
                  : catalog.modes.length
              } modes published. Triggers, worked examples, mitigations, and citations.`}
            />
            <NextTab
              href={`/c?method=${encodeURIComponent(METHOD_NAME)}`}
              label="Conclusions produced"
              body={`Public conclusions linked to this method. Currently ${
                entry?.conclusionsProduced ?? 0
              } published.`}
            />
          </ul>
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
    <div className="public-card" style={{ padding: "0.75rem 0.9rem" }}>
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
      <div style={{ fontSize: "1.2rem", fontWeight: 600, color }}>{value}</div>
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
