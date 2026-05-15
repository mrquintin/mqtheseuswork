import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { getApprovedFormalisationForPrinciple } from "@/lib/quantitativeFormalisationApi";

/**
 * /principles/[id] — public principle detail page.
 *
 * Round 21 rewrite of the canonical principle surface. Previously the
 * detail lived at /methodology/principles/[id]; that path now 308s to
 * here.
 *
 * Layout, top to bottom (every section hides when empty so no panel
 * shows an empty box):
 *
 *   1. Principle statement.
 *   2. principle_kind badge + domain.
 *   3. "What would update this" — APPROVED quantitative
 *      formalisation (prompt 57). Hidden if no APPROVED row.
 *   4. "Evidence FOR" — cluster conclusions that cite or support the
 *      principle.
 *   5. "Evidence AGAINST" — open-tier conclusions or contradictions
 *      that would weaken it (omitted when none).
 *   6. "Decisions this informs" — `decisionExamples` lifted from the
 *      underlying conclusions (deduped).
 *   7. "Source artifacts" — raw uploaded materials with the verbatim
 *      `sourceSpan` preserved per citation rules.
 *   8. "Lineage" — link out to the temporal-lineage view.
 */

type Params = { id: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { id } = await params;
  const p = await db.principle.findFirst({
    where: { id, status: "accepted", publicVisible: true },
    select: { text: true },
  });
  if (!p) return { title: "Principle · Theseus" };
  return {
    title: `${p.text.slice(0, 70)} · Theseus principle`,
    description:
      "A principle the firm has re-derived enough to defend, with the evidence for and against, the decisions it informs, and the quantitative test that would update it.",
  };
}

export const dynamic = "force-dynamic";

const PRINCIPLE_KINDS = [
  "RULE",
  "CRITERION",
  "MECHANISM",
  "HEURISTIC",
  "DEFINITION",
  "FORMULA",
  "ALGORITHM",
] as const;
type PrincipleKindKey = (typeof PRINCIPLE_KINDS)[number];

function safeJsonStringArray(value: string): string[] {
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((x): x is string => typeof x === "string");
  } catch {
    return [];
  }
}

function isPrincipleKind(value: string | null | undefined): value is PrincipleKindKey {
  return value != null && (PRINCIPLE_KINDS as ReadonlyArray<string>).includes(value);
}

function aggregateKind(kinds: Array<string | null>): PrincipleKindKey | "UNSPECIFIED" {
  const counts = new Map<PrincipleKindKey, number>();
  for (const raw of kinds) {
    if (isPrincipleKind(raw)) counts.set(raw, (counts.get(raw) ?? 0) + 1);
  }
  if (counts.size === 0) return "UNSPECIFIED";
  let best: { kind: PrincipleKindKey; count: number } | null = null;
  for (const [kind, count] of counts) {
    if (!best || count > best.count) best = { kind, count };
  }
  return best!.kind;
}

export default async function PublicPrincipleDetailPage({
  params,
}: {
  params: Promise<Params>;
}) {
  const { id } = await params;
  const founder = await getFounder();

  const principle = await db.principle.findFirst({
    where: { id, status: "accepted", publicVisible: true },
  });
  if (!principle) notFound();

  const domains = safeJsonStringArray(principle.domainsJson);
  const clusterIds = safeJsonStringArray(principle.clusterConclusionIds);
  const citedIds = new Set(safeJsonStringArray(principle.citedConclusionIds));

  const [clusterConclusions, formalisation] = await Promise.all([
    fetchClusterConclusions(clusterIds),
    getApprovedFormalisationForPrinciple(id),
  ]);

  // Prompt 63 runner: the most recent QuantitativeTestResult for the
  // approved formalisation. Hidden when no formalisation exists or the
  // runner has not yet emitted a row.
  const latestTestResult = formalisation
    ? await fetchLatestTestResult(formalisation.id)
    : null;

  const aggregatedKind = aggregateKind(
    clusterConclusions.map((c) => c.principleKind),
  );

  // Evidence FOR — cluster conclusions the LLM cited, plus any other
  // cluster conclusion at firm/founder tier. Open-tier rows fall to
  // Evidence AGAINST so the reader sees what would weaken the claim.
  const evidenceFor = clusterConclusions.filter((c) => {
    if (citedIds.has(c.id)) return true;
    return c.confidenceTier === "firm" || c.confidenceTier === "founder";
  });
  const evidenceAgainst = clusterConclusions.filter(
    (c) => !citedIds.has(c.id) && c.confidenceTier === "open",
  );

  // Decisions this informs — union of all `decisionExamples` arrays
  // across the cluster, deduped.
  const decisions = (() => {
    const seen = new Set<string>();
    const out: Array<{ conclusionId: string; example: string }> = [];
    for (const c of clusterConclusions) {
      for (const example of safeJsonStringArray(c.decisionExamples)) {
        const trimmed = example.trim();
        if (!trimmed) continue;
        if (seen.has(trimmed.toLowerCase())) continue;
        seen.add(trimmed.toLowerCase());
        out.push({ conclusionId: c.id, example: trimmed });
      }
    }
    return out;
  })();

  // Source artifacts — distinct public-visible uploads with the
  // verbatim `sourceSpan` preserved next to the upload that produced
  // it. Private/semi-private uploads are dropped so the public surface
  // never leaks them.
  const sourceArtifacts = (() => {
    const seen = new Set<string>();
    const out: Array<{
      uploadId: string;
      title: string;
      slug: string | null;
      conclusionId: string;
      quotedSpan: string | null;
    }> = [];
    for (const c of clusterConclusions) {
      for (const link of c.sources) {
        const u = link.upload;
        if (!u) continue;
        if (u.visibility && u.visibility !== "public") continue;
        if (!u.publishedAt) continue;
        const key = `${u.id}:${c.id}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({
          uploadId: u.id,
          title: u.title,
          slug: u.slug,
          conclusionId: c.id,
          quotedSpan: c.sourceSpan,
        });
      }
    }
    return out;
  })();

  // Lineage — the first cluster conclusion is the "anchor" for the
  // lineage view (Round 18 prompt 23 keyed lineage off conclusion id).
  const lineageAnchorId = clusterConclusions[0]?.id ?? null;

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main
        id="principle-main"
        className="public-container public-methodology-page"
        data-testid="principle-detail"
      >
        <section className="public-section">
          <p>
            <Link
              href="/principles"
              className="mono"
              style={{
                fontSize: "0.65rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: "var(--amber, #d4a017)",
                textDecoration: "none",
              }}
            >
              ← all principles
            </Link>
          </p>
          {/* 1. Principle statement */}
          <h1
            className="public-title"
            style={{ marginTop: "0.6rem" }}
            data-testid="principle-statement"
          >
            {principle.text}
          </h1>

          {/* 2. kind badge + domain */}
          <div
            className="mono"
            data-testid="principle-meta"
            style={{
              marginTop: "0.7rem",
              fontSize: "0.6rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              color: "var(--public-muted, #888)",
              display: "flex",
              flexWrap: "wrap",
              gap: "0.5rem",
              alignItems: "center",
            }}
          >
            <span
              data-testid="principle-kind-badge"
              style={{
                padding: "0.18rem 0.55rem",
                border: "1px solid var(--amber, #d4a017)",
                color: "var(--amber, #d4a017)",
              }}
            >
              {aggregatedKind.toLowerCase()}
            </span>
            {domains.map((d) => (
              <span
                key={d}
                style={{
                  padding: "0.18rem 0.55rem",
                  border: "1px solid var(--public-muted, #888)",
                }}
              >
                {d}
              </span>
            ))}
            <span>conviction · {principle.convictionScore.toFixed(2)}</span>
            <span>domains · {principle.domainBreadth}</span>
          </div>
        </section>

        {/* 3. "What would update this" — quantitative formalisation. */}
        {formalisation ? (
          <section
            className="public-section"
            aria-labelledby="how-we-test-title"
            data-testid="section-formalisation"
          >
            <h2 id="how-we-test-title">What would update this</h2>
            <p className="public-muted">
              The firm has approved a quantitative formalisation for
              this principle — the null hypothesis, the tests we would
              run, the datasets we would hit, and the readings that
              would shift our confidence.
            </p>
            <div
              className="public-card"
              style={{ padding: "1.1rem 1.3rem", marginTop: "1rem" }}
            >
              <h3 className="mono" style={publicSubheadingStyle}>
                Null hypothesis
              </h3>
              <p style={{ marginTop: "0.4rem" }}>{formalisation.nullHypothesis}</p>
            </div>
            {formalisation.tests.length > 0 ? (
              <div
                className="public-card"
                style={{ padding: "1.1rem 1.3rem", marginTop: "0.85rem" }}
              >
                <h3 className="mono" style={publicSubheadingStyle}>
                  Tests · {formalisation.tests.length}
                </h3>
                <ul style={listStyle}>
                  {formalisation.tests.map((t, i) => (
                    <li key={i} style={listItemStyle}>
                      <span className="mono" style={{ fontSize: "0.65rem" }}>
                        {t.kind}
                      </span>{" "}
                      — <strong>{t.dependent}</strong>
                      {t.independents.length > 0
                        ? ` ~ ${t.independents.join(" + ")}`
                        : ""}
                      {t.controls.length > 0
                        ? ` (controls: ${t.controls.join(", ")})`
                        : ""}
                      <br />
                      <span className="public-muted" style={{ fontSize: "0.85rem" }}>
                        expected: {t.expected_sign_or_magnitude} at p &lt;{" "}
                        {t.expected_p_threshold}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {formalisation.dataSources.length > 0 ? (
              <div
                className="public-card"
                style={{ padding: "1.1rem 1.3rem", marginTop: "0.85rem" }}
              >
                <h3 className="mono" style={publicSubheadingStyle}>
                  Data sources · {formalisation.dataSources.length}
                </h3>
                <ul style={listStyle}>
                  {formalisation.dataSources.map((d, i) => (
                    <li key={i} style={listItemStyle}>
                      <strong>{d.name}</strong> — {d.provenance}
                      <br />
                      <span className="public-muted" style={{ fontSize: "0.85rem" }}>
                        license: {d.license} · refresh: {d.refresh_cadence}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {formalisation.decisionThresholds.length > 0 ? (
              <div
                className="public-card"
                style={{ padding: "1.1rem 1.3rem", marginTop: "0.85rem" }}
              >
                <h3 className="mono" style={publicSubheadingStyle}>
                  Decision thresholds
                </h3>
                <ul style={listStyle}>
                  {formalisation.decisionThresholds.map((t, i) => (
                    <li key={i} style={listItemStyle}>
                      {t}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {latestTestResult ? (
              <div
                className="public-card"
                style={{ padding: "1.1rem 1.3rem", marginTop: "0.85rem" }}
                data-testid="section-latest-test-result"
              >
                <h3 className="mono" style={publicSubheadingStyle}>
                  Latest test result · {latestTestResult.runStamp}
                </h3>
                <p style={{ marginTop: "0.45rem" }}>
                  {latestTestResult.decisionSummary || "No summary recorded."}
                </p>
                {Object.keys(latestTestResult.metricValues).length > 0 ? (
                  <ul style={listStyle}>
                    {Object.entries(latestTestResult.metricValues).map(
                      ([name, snapshot]) => (
                        <li key={name} style={listItemStyle}>
                          <strong>{name}</strong> ·{" "}
                          {snapshot.value === null || snapshot.value === undefined
                            ? "n/a"
                            : typeof snapshot.value === "number"
                              ? snapshot.value.toFixed(4)
                              : String(snapshot.value)}
                          {snapshot.as_of ? (
                            <span
                              className="public-muted"
                              style={{ fontSize: "0.85rem" }}
                            >
                              {" "}· as of {snapshot.as_of}
                            </span>
                          ) : null}
                        </li>
                      ),
                    )}
                  </ul>
                ) : null}
                {latestTestResult.artifactsPath ? (
                  <p style={{ marginTop: "0.6rem" }}>
                    <Link
                      href={`/api/principles/${id}/quantitative/${latestTestResult.id}/artifacts`}
                      className="mono"
                      data-testid="latest-test-artifacts-link"
                      style={{
                        fontSize: "0.6rem",
                        letterSpacing: "0.22em",
                        textTransform: "uppercase",
                        color: "var(--amber, #d4a017)",
                        textDecoration: "none",
                      }}
                    >
                      View artifacts
                    </Link>
                  </p>
                ) : null}
                {latestTestResult.thresholdCrossings.length > 0 ? (
                  <p
                    className="public-muted"
                    style={{ marginTop: "0.6rem", fontSize: "0.85rem" }}
                  >
                    Decision thresholds crossed — pending founder review:
                    {" "}
                    {latestTestResult.thresholdCrossings.join("; ")}
                  </p>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}

        {/* 4. Evidence FOR */}
        {evidenceFor.length > 0 ? (
          <section
            className="public-section"
            aria-labelledby="evidence-for-title"
            data-testid="section-evidence-for"
          >
            <h2 id="evidence-for-title">Evidence for</h2>
            <p className="public-muted">
              Conclusions the firm has recorded that cite this principle
              or sit in its supporting cluster.
            </p>
            <ul style={listStyle}>
              {evidenceFor.map((c) => (
                <li key={c.id} style={listItemStyle}>
                  <Link
                    href={`/c/${c.id}`}
                    style={{ color: "inherit", textDecoration: "none" }}
                  >
                    {c.text}
                  </Link>
                  <div
                    className="mono"
                    style={{
                      marginTop: "0.3rem",
                      fontSize: "0.55rem",
                      letterSpacing: "0.22em",
                      textTransform: "uppercase",
                      color: "var(--public-muted, #888)",
                    }}
                  >
                    tier · {c.confidenceTier}
                    {citedIds.has(c.id) ? " · cited by principle draft" : ""}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* 5. Evidence AGAINST — only when present */}
        {evidenceAgainst.length > 0 ? (
          <section
            className="public-section"
            aria-labelledby="evidence-against-title"
            data-testid="section-evidence-against"
          >
            <h2 id="evidence-against-title">Evidence against</h2>
            <p className="public-muted">
              Open-tier conclusions in the same cluster — claims the
              firm has not yet promoted to firm or founder confidence,
              and which would weaken this principle if they hold up.
            </p>
            <ul style={listStyle}>
              {evidenceAgainst.map((c) => (
                <li key={c.id} style={listItemStyle}>
                  <Link
                    href={`/c/${c.id}`}
                    style={{ color: "inherit", textDecoration: "none" }}
                  >
                    {c.text}
                  </Link>
                  <div
                    className="mono"
                    style={{
                      marginTop: "0.3rem",
                      fontSize: "0.55rem",
                      letterSpacing: "0.22em",
                      textTransform: "uppercase",
                      color: "var(--public-muted, #888)",
                    }}
                  >
                    tier · {c.confidenceTier}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* 6. Decisions this informs */}
        {decisions.length > 0 ? (
          <section
            className="public-section"
            aria-labelledby="decisions-title"
            data-testid="section-decisions"
          >
            <h2 id="decisions-title">Decisions this informs</h2>
            <p className="public-muted">
              Example decisions the firm would consult this principle
              for. Each links to the conclusion that registered the
              example.
            </p>
            <ul style={listStyle}>
              {decisions.map((d, i) => (
                <li key={i} style={listItemStyle}>
                  <Link
                    href={`/c/${d.conclusionId}`}
                    style={{ color: "inherit", textDecoration: "none" }}
                  >
                    {d.example}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* 7. Source artifacts */}
        {sourceArtifacts.length > 0 ? (
          <section
            className="public-section"
            aria-labelledby="sources-title"
            data-testid="section-sources"
          >
            <h2 id="sources-title">Source artifacts</h2>
            <p className="public-muted">
              The raw uploads the underlying conclusions were extracted
              from, with the verbatim span the principle was lifted from
              preserved.
            </p>
            <ul style={listStyle}>
              {sourceArtifacts.map((s) => (
                <li key={`${s.uploadId}-${s.conclusionId}`} style={listItemStyle}>
                  {s.slug ? (
                    <Link
                      href={`/post/${s.slug}`}
                      style={{
                        color: "inherit",
                        textDecoration: "none",
                        fontFamily: "'EB Garamond', serif",
                      }}
                    >
                      {s.title}
                    </Link>
                  ) : (
                    <span style={{ fontFamily: "'EB Garamond', serif" }}>
                      {s.title}
                    </span>
                  )}
                  {s.quotedSpan ? (
                    <blockquote
                      data-testid="quoted-span"
                      style={{
                        margin: "0.55rem 0 0",
                        padding: "0.45rem 0.7rem",
                        borderLeft: "2px solid var(--public-muted, #888)",
                        fontFamily: "'EB Garamond', serif",
                        fontSize: "0.95rem",
                        color: "var(--public-muted, #888)",
                      }}
                    >
                      “{s.quotedSpan}”
                    </blockquote>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {/* 8. Lineage link */}
        {lineageAnchorId ? (
          <section
            className="public-section"
            aria-labelledby="lineage-title"
            data-testid="section-lineage"
          >
            <h2 id="lineage-title">Lineage</h2>
            <p className="public-muted">
              The temporal lineage view stitches every step that
              produced this principle — sources, claim extraction,
              methodology profiles, reviews — into a single trace.
            </p>
            <p style={{ marginTop: "0.7rem" }}>
              <Link
                href={`/api/public/conclusion/${lineageAnchorId}/lineage`}
                className="mono"
                style={{
                  display: "inline-block",
                  padding: "0.55rem 1.1rem",
                  border: "1px solid var(--amber, #d4a017)",
                  color: "var(--amber, #d4a017)",
                  textDecoration: "none",
                  fontSize: "0.65rem",
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                }}
              >
                Open lineage
              </Link>
            </p>
          </section>
        ) : null}
      </main>
    </>
  );
}

const publicSubheadingStyle: React.CSSProperties = {
  fontSize: "0.65rem",
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: "var(--amber, #d4a017)",
  margin: 0,
};

const listStyle: React.CSSProperties = {
  listStyle: "none",
  padding: 0,
  margin: "0.6rem 0 0",
  display: "flex",
  flexDirection: "column",
  gap: "0.55rem",
};

const listItemStyle: React.CSSProperties = {
  padding: "0.55rem 0.7rem",
  borderLeft: "2px solid var(--amber, #d4a017)",
};

type ClusterConclusion = {
  id: string;
  text: string;
  confidenceTier: string;
  confidence: number;
  principleKind: string | null;
  domainOfApplicability: string | null;
  decisionExamples: string;
  sourceSpan: string | null;
  topicHint: string;
  sources: Array<{
    upload: {
      id: string;
      title: string;
      slug: string | null;
      publishedAt: Date | null;
      visibility: string | null;
    };
  }>;
};

/**
 * Schema-lag-tolerant read for the principle's cluster conclusions.
 *
 * Issued without `select` so the generated Prisma client doesn't
 * complain about Round-21 columns it hasn't seen yet (`principleKind`,
 * `decisionExamples`, `sourceSpan`); the runtime row carries them, and
 * the `unknown` cast bridges the projection back to the precise shape
 * this page consumes. Mirrors the schema-lag pattern used in
 * `quantitativeFormalisationApi.ts`.
 */
type LatestTestResult = {
  id: string;
  runStamp: string;
  decisionSummary: string;
  artifactsPath: string;
  thresholdCrossings: string[];
  metricValues: Record<string, { value: number | null; as_of?: string }>;
};

/**
 * Read the most-recent QuantitativeTestResult for a formalisation.
 *
 * Schema-lag tolerant for the same reason as fetchClusterConclusions:
 * the generated Prisma client may not yet know about the prompt-63
 * runner table on a fresh checkout, but the runtime row carries the
 * fields. Returns ``null`` if the table or row is absent.
 */
async function fetchLatestTestResult(
  formalisationId: string,
): Promise<LatestTestResult | null> {
  type Row = {
    id: string;
    runStamp: string;
    decisionSummary: string | null;
    artifactsPath: string | null;
    metricValuesJson: string | null;
    thresholdCrossingsJson: string | null;
  };
  // @ts-expect-error — generated client may lag; the model exists in
  // schema.prisma and the runtime resolves once `prisma generate` runs.
  const row: Row | null = await db.quantitativeTestResult?.findFirst({
    where: { formalisationId },
    orderBy: { createdAt: "desc" },
  });
  if (!row) return null;
  let metricValues: LatestTestResult["metricValues"] = {};
  try {
    const parsed = JSON.parse(row.metricValuesJson ?? "{}");
    if (parsed && typeof parsed === "object") {
      metricValues = parsed as LatestTestResult["metricValues"];
    }
  } catch {
    metricValues = {};
  }
  let thresholdCrossings: string[] = [];
  try {
    const parsed = JSON.parse(row.thresholdCrossingsJson ?? "[]");
    if (Array.isArray(parsed)) {
      thresholdCrossings = parsed.filter(
        (x): x is string => typeof x === "string",
      );
    }
  } catch {
    thresholdCrossings = [];
  }
  return {
    id: row.id,
    runStamp: row.runStamp,
    decisionSummary: row.decisionSummary ?? "",
    artifactsPath: row.artifactsPath ?? "",
    thresholdCrossings,
    metricValues,
  };
}

async function fetchClusterConclusions(
  clusterIds: string[],
): Promise<ClusterConclusion[]> {
  if (clusterIds.length === 0) return [];
  const rows = (await db.conclusion.findMany({
    where: { id: { in: clusterIds } },
    include: {
      sources: {
        select: {
          upload: {
            select: {
              id: true,
              title: true,
              slug: true,
              publishedAt: true,
              visibility: true,
            },
          },
        },
      },
    },
  })) as unknown as ClusterConclusion[];
  return rows.map((r) => ({
    id: r.id,
    text: r.text,
    confidenceTier: r.confidenceTier,
    confidence: r.confidence,
    principleKind: r.principleKind ?? null,
    domainOfApplicability: r.domainOfApplicability ?? null,
    decisionExamples: r.decisionExamples ?? "[]",
    sourceSpan: r.sourceSpan ?? null,
    topicHint: r.topicHint ?? "",
    sources: r.sources ?? [],
  }));
}
