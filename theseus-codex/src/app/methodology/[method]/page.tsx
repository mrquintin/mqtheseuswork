import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Prisma } from "@prisma/client";

import MethodCrossLinks, { ReaderTrail } from "@/components/MethodCrossLinks";
import MethodTabs from "@/components/MethodTabs";
import PublicHeader from "@/components/PublicHeader";
import RetirementBanner, {
  type RetirementInfo,
  type RetirementState,
} from "@/components/RetirementBanner";
import SubscribeForm from "@/components/SubscribeForm";
import { getCatalog, publicModesForMethod } from "@/lib/failureModes";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { resolvePublicOrganizationId } from "@/lib/conclusionsRead";
import { loadPublicOpenQuestions } from "@/lib/openQuestionsApi";
import { listPublicPrinciples } from "@/lib/principlesApi";
import {
  buildMethodologyManifest,
  driftColor,
  driftLabel,
  type ManifestMethod,
} from "@/lib/methodologyManifest";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ method: string }>;
}): Promise<Metadata> {
  const { method } = await params;
  const methodName = decodeURIComponent(method);
  const entry = await methodEntryFromManifest(methodName);

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

/** Single manifest entry for a method. */
async function methodEntryFromManifest(
  methodName: string,
): Promise<ManifestMethod | null> {
  const manifest = await buildMethodologyManifest();
  return manifest.methods.find((m) => m.name === methodName) ?? null;
}

/**
 * Method overview page — v2.
 *
 * The Round 17 tabs were a linear strip; a reader had to walk them to
 * learn anything. v2 front-loads what an outsider actually needs on
 * first load — a one-line description, then three pills that jump
 * straight to what we tested, the track record, and how to challenge
 * the method — and demotes the tab strip to a secondary "detailed
 * sections" nav. The cross-link block puts every adjacent method,
 * question, and principle one click away. All of it is server-rendered
 * and works with JavaScript disabled.
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
  const manifest = await buildMethodologyManifest();
  const entry = manifest.methods.find((m) => m.name === methodName) ?? null;

  // Cross-link inputs. Composition is read straight off the manifest
  // edges; "composes" is what this method is built from, "depended on
  // by" is what builds on it. Open questions and principles touch the
  // database, so both are wrapped to degrade to an empty group rather
  // than fail the page.
  const composes = manifest.edges
    .filter((e) => e.src === methodName)
    .map((e) => e.dst)
    .sort();
  const dependedOnBy = manifest.edges
    .filter((e) => e.dst === methodName)
    .map((e) => e.src)
    .sort();
  const [openQuestions, principles, retirement] = await Promise.all([
    openQuestionsForMethod(methodName),
    principlesForMethod(methodName),
    retirementForMethod(methodName),
  ]);

  // Retired methods do not vanish from the public record — they render
  // with tombstone styling so a reader can see what the firm has
  // stopped trusting.
  const tombstoned =
    retirement?.state === "deprecated" || retirement?.state === "retired";

  const enc = encodeURIComponent(methodName);

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
        <h1
          className="public-title"
          style={{
            marginTop: "0.5rem",
            ...(tombstoned
              ? {
                  textDecoration: "line-through",
                  textDecorationThickness: "1px",
                  color: "var(--parchment-dim, #b8ad95)",
                  filter: "grayscale(0.4)",
                }
              : {}),
          }}
        >
          {tombstoned ? (
            <span aria-hidden style={{ marginRight: "0.4rem" }}>
              †
            </span>
          ) : null}
          <span style={{ fontFamily: "monospace" }}>{methodName}</span>
        </h1>
        <p className="public-muted" style={{ marginTop: "-0.4rem", fontSize: "0.85rem" }}>
          v{entry?.version ?? "—"} · {catalog.method}
          {retirement && retirement.state !== "active"
            ? ` · ${retirement.state.replace("_", " ")}`
            : ""}
        </p>
        <ReaderTrail current={methodName} />

        <RetirementBanner info={retirement} variant="public" />

        {/* One-line description — the first thing an outsider reads. */}
        <p
          style={{
            fontSize: "1.05rem",
            lineHeight: 1.55,
            margin: "1rem 0 1.25rem",
          }}
        >
          {entry?.description ||
            "This method is part of Theseus's published methodology."}
        </p>

        {/* Three pills: what we tested, track record, how to challenge. */}
        <nav
          aria-label="Method essentials"
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.6rem",
            marginBottom: "0.5rem",
          }}
        >
          <Pill
            href="/methodology/benchmark/qh"
            label="What we tested"
            detail="The firm's first-run benchmark"
          />
          <Pill
            href={`/methodology/${enc}/track-record`}
            label="Track record"
            detail={
              entry?.calibration
                ? `Calibration slope ${entry.calibration.slope.toFixed(2)} · n=${entry.calibration.sampleSize}`
                : "Calibration once the sample clears the publish gate"
            }
          />
          <Pill
            href="/critiques"
            label="How to challenge"
            detail="Targeted critique, with a bounty for severe ones"
          />
        </nav>

        <MethodCrossLinks
          method={methodName}
          composes={composes}
          dependedOnBy={dependedOnBy}
          openQuestions={openQuestions}
          principles={principles}
        />

        <section className="public-section" aria-label="At-a-glance metrics">
          <h2>At a glance</h2>
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

        {/* Tabs are now secondary: the full per-section detail, below
            the essentials and the cross-links. */}
        <section className="public-section">
          <h2>Detailed sections</h2>
          <p className="public-muted" style={{ marginTop: 0, fontSize: "0.85rem" }}>
            Each section has its own shareable URL.
          </p>
          <MethodTabs method={methodName} active="overview" />
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            <NextTab
              href={`/methodology/${enc}/track-record`}
              label="Track record"
              body="Calibration slope, weighted Brier, severity-pass rate, with a 90% bootstrap confidence band. Only published once the sample clears the publish gate."
            />
            <NextTab
              href={`/methodology/${enc}/domain`}
              label="Domain"
              body="Where the method is judged in-bounds, edge-case, or out-of-bounds, based on the recorded domain bound verdicts."
            />
            <NextTab
              href={`/methodology/composition#${enc}`}
              label="Composition"
              body="Where this method sits in the public-visible dependency graph — what it composes, what composes it."
            />
            <NextTab
              href={`/methodology/${enc}/failures`}
              label="Failure modes"
              body={`${publicModes.length} of ${
                catalog.failures === "deliberately-empty" ? 0 : catalog.modes.length
              } modes published. Triggers, worked examples, mitigations, and citations.`}
            />
            <NextTab
              href={`/c?method=${enc}`}
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

/**
 * Open questions for which this method is a recorded candidate. Wrapped
 * so a database hiccup degrades to an empty cross-link group instead of
 * failing the whole page.
 */
async function openQuestionsForMethod(
  methodName: string,
): Promise<{ id: string; summary: string }[]> {
  try {
    const organizationId = await resolvePublicOrganizationId();
    if (!organizationId) return [];
    const rows = await loadPublicOpenQuestions(organizationId, { limit: 80 });
    return rows
      .filter((r) => r.candidateMethodNames.includes(methodName))
      .map((r) => ({ id: r.id, summary: r.summary }));
  } catch {
    return [];
  }
}

/**
 * Principles whose evidence cluster includes a public conclusion this
 * method produced. The link is method → public conclusions →
 * principle clusters; both hops stay inside the public surface.
 */
async function principlesForMethod(
  methodName: string,
): Promise<{ id: string; text: string }[]> {
  try {
    const conclusionIds = await publicConclusionIdsForMethod(methodName);
    if (conclusionIds.length === 0) return [];
    const idSet = new Set(conclusionIds);
    const principles = await listPublicPrinciples();
    return principles
      .filter(
        (p) =>
          p.clusterConclusionIds.some((cid) => idSet.has(cid)) ||
          p.citedConclusionIds.some((cid) => idSet.has(cid)),
      )
      .map((p) => ({ id: p.id, text: p.text }));
  } catch {
    return [];
  }
}

/** Public-visible conclusion ids that used this method. */
async function publicConclusionIdsForMethod(
  methodName: string,
): Promise<string[]> {
  try {
    const rows = await db.$queryRaw<{ conclusionId: string }[]>(
      Prisma.sql`SELECT DISTINCT cm."conclusionId" AS "conclusionId"
                   FROM "ConclusionMethod" cm
                   JOIN "PublishedConclusion" pc
                     ON pc."sourceConclusionId" = cm."conclusionId"
                    AND pc."organizationId" = cm."organizationId"
                  WHERE cm."methodName" = ${methodName}`,
    );
    return rows.map((r) => r.conclusionId);
  } catch {
    return [];
  }
}

/**
 * Retirement state for this method, for the public methodology surface.
 * Wrapped in try/catch so the page degrades to "no retirement record"
 * on a DB without the `MethodRetirement` table — retired methods are
 * part of the firm's record, but a missing mirror table must not blank
 * the page.
 */
async function retirementForMethod(
  methodName: string,
): Promise<RetirementInfo | null> {
  try {
    const organizationId = await resolvePublicOrganizationId();
    if (!organizationId) return null;
    const rows = await db.$queryRaw<
      Array<{
        state: string;
        replacement: string | null;
        rationale: string | null;
        reviewOpenedAt: Date | string | null;
        deprecatedAt: Date | string | null;
        retiredAt: Date | string | null;
        sunsetAt: Date | string | null;
      }>
    >(
      Prisma.sql`SELECT state, replacement, rationale,
                        "reviewOpenedAt", "deprecatedAt", "retiredAt", "sunsetAt"
                   FROM "MethodRetirement"
                  WHERE "organizationId" = ${organizationId}
                    AND "methodName" = ${methodName}
                  LIMIT 1`,
    );
    if (rows.length === 0) return null;
    const r = rows[0];
    const iso = (v: Date | string | null) =>
      v == null ? null : v instanceof Date ? v.toISOString() : String(v);
    const allowed = ["active", "under_review", "deprecated", "retired"] as const;
    const state = (allowed as readonly string[]).includes(r.state)
      ? (r.state as RetirementState)
      : "active";
    return {
      state,
      replacement: r.replacement || null,
      rationale: r.rationale || "",
      reviewOpenedAt: iso(r.reviewOpenedAt),
      deprecatedAt: iso(r.deprecatedAt),
      retiredAt: iso(r.retiredAt),
      sunsetAt: iso(r.sunsetAt),
    };
  } catch {
    return null;
  }
}

function Pill({
  href,
  label,
  detail,
}: {
  href: string;
  label: string;
  detail: string;
}) {
  return (
    <Link
      href={href}
      className="public-card public-method-card"
      style={{
        display: "block",
        flex: "1 1 200px",
        textDecoration: "none",
        color: "inherit",
        padding: "0.7rem 0.95rem",
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          color: "var(--amber, #d4a017)",
          marginBottom: "0.3rem",
        }}
      >
        {label} →
      </div>
      <div className="public-muted" style={{ fontSize: "0.8rem", lineHeight: 1.4 }}>
        {detail}
      </div>
    </Link>
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
