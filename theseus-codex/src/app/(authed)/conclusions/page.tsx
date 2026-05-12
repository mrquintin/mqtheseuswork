import Link from "next/link";
import { Suspense } from "react";
import TemporalReplayBar from "@/components/TemporalReplayBar";
import ConfidenceTierSigil from "@/components/ConfidenceTierSigil";
import Excerpt from "@/components/Excerpt";
import { db } from "@/lib/db";
import { founderDisplayName } from "@/lib/founderDisplay";
import { fetchReplayConclusions } from "@/lib/noosphereReplayBridge";
import { AS_OF_ISO } from "@/lib/replayDate";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Conclusions list. Each row shows the inline confidence-tier sigil
 * (firm / founder / open / retired) next to the text, so a glance down
 * the page reveals the firm's belief-structure at a glance.
 *
 * Filter chips at the top use the same sigil as a prefix, reinforcing
 * the semantic colour-coding.
 */

const TIERS = ["firm", "founder", "open", "retired"] as const;
const PAGE_SIZE = 40;

type ConclusionsSearchParams = {
  tier?: string;
  topic?: string;
  asOf?: string;
  q?: string;
  page?: string;
  tab?: string;
};

function urlFor(basePath: string, tab: string, params: URLSearchParams) {
  if (basePath === "/knowledge") params.set("tab", tab);
  const qs = params.toString();
  return `${basePath}${qs ? `?${qs}` : ""}`;
}

async function ConclusionsContent({
  searchParams,
  basePath,
}: {
  searchParams: Promise<ConclusionsSearchParams>;
  basePath?: string;
}) {
  const sp = await searchParams;
  const asOf = sp.asOf;
  const replay = Boolean(asOf && AS_OF_ISO.test(asOf));
  // When this component is rendered inside the /knowledge tab shell, sp
  // carries `tab=conclusions`. Detect that so form submits and pagination
  // round-trip back to /knowledge?tab=conclusions instead of dropping the
  // user into the bare /conclusions route.
  const resolvedBasePath =
    basePath ?? (sp.tab === "conclusions" ? "/knowledge" : "/conclusions");

  if (replay) {
    const { rows, error } = await fetchReplayConclusions(asOf!);
    return (
      <main style={{ maxWidth: "1000px", margin: "0 auto", padding: "1.5rem 2rem 3rem" }}>
        <Suspense fallback={null}>
          <TemporalReplayBar />
        </Suspense>
        <h2
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.06em",
            fontSize: "1.2rem",
            fontWeight: 500,
            margin: "0 0 0.4rem",
          }}
        >
          Conclusions
        </h2>
        <p
          style={{
            color: "var(--ember)",
            fontSize: "0.8rem",
            margin: "0 0 1rem",
          }}
        >
          Replay mode — as of <strong>{asOf}</strong>.
        </p>
        {error ? (
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
            {error}
          </p>
        ) : null}
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "grid",
            gap: "0.6rem",
          }}
        >
          {rows.map((c) => (
            <li
              key={c.id}
              className="portal-card"
              style={{
                padding: "0.85rem 1rem",
                display: "grid",
                gridTemplateColumns: "auto 1fr",
                gap: "0.75rem",
                alignItems: "flex-start",
              }}
            >
              <ConfidenceTierSigil tier={c.confidence_tier || "open"} />
              <div style={{ minWidth: 0 }}>
                <Link
                  href={`/conclusions/${c.id}`}
                  style={{
                    textDecoration: "none",
                    color: "inherit",
                    display: "block",
                  }}
                >
                  <div
                    className="mono"
                    style={{
                      fontSize: "0.6rem",
                      color: "var(--amber-dim)",
                      textTransform: "uppercase",
                      letterSpacing: "0.12em",
                      display: "flex",
                      gap: "0.5rem",
                      flexWrap: "wrap",
                    }}
                  >
                    <span>{c.confidence_tier || ""}</span>
                    {c.created_at ? (
                      <span>
                        · {String(c.created_at).slice(0, 10)}
                      </span>
                    ) : null}
                    <span style={{ color: "var(--ember)", marginLeft: "auto" }}>
                      replay
                    </span>
                  </div>
                  <p style={{ margin: "0.3rem 0 0", color: "var(--parchment)", lineHeight: 1.45 }}>
                    {c.text}
                  </p>
                </Link>
                {c.rationale ? (
                  <Excerpt
                    text={c.rationale}
                    lines={2}
                    style={{
                      marginTop: "0.3rem",
                      fontSize: "0.8rem",
                      color: "var(--parchment-dim)",
                      lineHeight: 1.5,
                    }}
                  />
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </main>
    );
  }

  const tenant = await requireTenantContext();
  if (!tenant) {
    return null;
  }

  const page = Math.max(1, parseInt(sp.page || "1", 10));
  const q = sp.q?.trim() || "";

  const where: {
    organizationId: string;
    confidenceTier?: string;
    topicHint?: { contains: string };
    OR?: Array<Record<string, { contains: string; mode: "insensitive" }>>;
  } = { organizationId: tenant.organizationId };
  if (sp.tier) where.confidenceTier = sp.tier;
  if (sp.topic) where.topicHint = { contains: sp.topic };
  if (q) {
    where.OR = [
      { text: { contains: q, mode: "insensitive" } },
      { rationale: { contains: q, mode: "insensitive" } },
      { topicHint: { contains: q, mode: "insensitive" } },
    ];
  }

  const [rows, total] = await Promise.all([
    db.conclusion.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: PAGE_SIZE + 1,
      skip: (page - 1) * PAGE_SIZE,
      include: {
        attributedFounder: {
          select: { displayName: true, name: true, username: true },
        },
        sources: {
          take: 1,
          select: {
            upload: { select: { id: true, title: true, sourceType: true } },
          },
        },
      },
    }),
    db.conclusion.count({ where }),
  ]);
  const hasNext = rows.length > PAGE_SIZE;
  const display = hasNext ? rows.slice(0, PAGE_SIZE) : rows;

  // Page URLs preserve filter state; tier chips reset `page` so the
  // new filter's first page is always what the user sees after clicking.
  function buildPageUrl(p: number): string {
    const params = new URLSearchParams();
    if (sp.tier) params.set("tier", sp.tier);
    if (sp.topic) params.set("topic", sp.topic);
    if (q) params.set("q", q);
    if (p > 1) params.set("page", String(p));
    return urlFor(resolvedBasePath, "conclusions", params);
  }

  function buildTierUrl(tier: string | null): string {
    const params = new URLSearchParams();
    if (tier) params.set("tier", tier);
    if (q) params.set("q", q);
    return urlFor(resolvedBasePath, "conclusions", params);
  }

  function buildClearUrl(): string {
    const params = new URLSearchParams();
    if (sp.tier) params.set("tier", sp.tier);
    if (sp.topic) params.set("topic", sp.topic);
    return urlFor(resolvedBasePath, "conclusions", params);
  }

  function buildTopicUrl(topic: string): string {
    const params = new URLSearchParams();
    if (topic) params.set("topic", topic);
    if (sp.tier) params.set("tier", sp.tier);
    if (q) params.set("q", q);
    return urlFor(resolvedBasePath, "conclusions", params);
  }

  const inKnowledgeShell = resolvedBasePath === "/knowledge";

  return (
    <main
      style={{
        maxWidth: "1000px",
        margin: "0 auto",
        padding: inKnowledgeShell ? "1rem 1.5rem 3rem" : "1.5rem 1.5rem 3rem",
      }}
    >
      <Suspense fallback={null}>
        <TemporalReplayBar />
      </Suspense>

      {!inKnowledgeShell ? (
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.06em",
            fontSize: "1.3rem",
            fontWeight: 500,
            margin: "0 0 1rem",
          }}
        >
          Conclusions
        </h1>
      ) : null}

      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 5,
          background: "var(--stone-black, #0a0a0a)",
          padding: "0.5rem 0 0.75rem",
          marginBottom: "0.75rem",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <form
          action={resolvedBasePath}
          method="get"
          style={{
            display: "flex",
            gap: "0.4rem",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          {inKnowledgeShell ? (
            <input type="hidden" name="tab" value="conclusions" />
          ) : null}
          <input
            type="text"
            name="q"
            defaultValue={q}
            placeholder="Search conclusions…"
            style={{
              flex: "1 1 14rem",
              minWidth: 0,
              padding: "0.35rem 0.6rem",
              fontSize: "0.85rem",
              fontFamily: "inherit",
              background: "transparent",
              border: "1px solid var(--border)",
              color: "var(--parchment)",
              borderRadius: 2,
            }}
          />
          {sp.tier && <input type="hidden" name="tier" value={sp.tier} />}
          {sp.topic && <input type="hidden" name="topic" value={sp.topic} />}
          <button
            type="submit"
            className="btn"
            style={{ fontSize: "0.62rem", padding: "0.3rem 0.65rem" }}
          >
            Search
          </button>
          {q ? (
            <Link
              href={buildClearUrl()}
              className="btn"
              style={{
                fontSize: "0.62rem",
                padding: "0.3rem 0.65rem",
                textDecoration: "none",
              }}
            >
              Clear
            </Link>
          ) : null}
        </form>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.35rem",
            marginTop: "0.5rem",
            alignItems: "center",
          }}
        >
          <span
            className="mono"
            style={{
              color: "var(--amber-dim)",
              fontSize: "0.58rem",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              marginRight: "0.25rem",
            }}
          >
            Tier
          </span>
          <Link
            href={buildTierUrl(null)}
            className="btn"
            style={{
              fontSize: "0.62rem",
              padding: "0.25rem 0.55rem",
              textDecoration: "none",
              ...(sp.tier ? {} : { borderColor: "var(--amber)", color: "var(--amber)" }),
            }}
          >
            All
          </Link>
          {TIERS.map((t) => (
            <Link
              key={t}
              href={buildTierUrl(t)}
              className="btn"
              style={{
                fontSize: "0.62rem",
                padding: "0.25rem 0.55rem",
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.35rem",
                ...(sp.tier === t
                  ? { borderColor: "var(--amber)", color: "var(--amber)" }
                  : {}),
              }}
            >
              <ConfidenceTierSigil tier={t} size="0.5rem" />
              <span>{t}</span>
            </Link>
          ))}
          <span
            style={{
              width: 1,
              height: "1rem",
              background: "var(--border)",
              margin: "0 0.25rem",
            }}
          />
          {sp.topic ? (
            <Link
              href={buildTopicUrl("")}
              className="btn"
              style={{
                fontSize: "0.62rem",
                padding: "0.25rem 0.55rem",
                textDecoration: "none",
                borderColor: "var(--amber)",
                color: "var(--amber)",
              }}
            >
              topic: {sp.topic} ✕
            </Link>
          ) : (
            <Link
              href={buildTopicUrl("method")}
              className="btn"
              style={{
                fontSize: "0.62rem",
                padding: "0.25rem 0.55rem",
                textDecoration: "none",
              }}
            >
              topic: method
            </Link>
          )}
        </div>

        {q ? (
          <p
            style={{
              fontSize: "0.7rem",
              color: "var(--parchment-dim)",
              margin: "0.45rem 0 0",
            }}
          >
            {total} result{total !== 1 ? "s" : ""} for &ldquo;{q}&rdquo;
          </p>
        ) : null}
      </div>

      {display.length === 0 ? (
        <div
          className="portal-card"
          style={{
            padding: "1.25rem",
            textAlign: "center",
            color: "var(--parchment-dim)",
            fontSize: "0.9rem",
          }}
        >
          No conclusions match the current filters.
        </div>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "grid",
            gap: "0.55rem",
          }}
        >
          {display.map((c) => {
            const sourceUpload = c.sources?.[0]?.upload;
            const confidencePct =
              typeof c.confidence === "number" && c.confidence > 0
                ? Math.round(c.confidence * 100)
                : null;
            return (
              <li
                key={c.id}
                className="portal-card"
                style={{
                  padding: "0.8rem 1rem",
                  display: "grid",
                  gridTemplateColumns: "auto 1fr",
                  gap: "0.75rem",
                  alignItems: "flex-start",
                }}
              >
                <ConfidenceTierSigil tier={c.confidenceTier} />
                <div style={{ minWidth: 0 }}>
                  <Link
                    href={`/conclusions/${c.id}`}
                    style={{
                      textDecoration: "none",
                      color: "inherit",
                      display: "block",
                    }}
                  >
                    <div
                      className="mono"
                      style={{
                        fontSize: "0.58rem",
                        color: "var(--amber-dim)",
                        textTransform: "uppercase",
                        letterSpacing: "0.14em",
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "0.4rem",
                        alignItems: "center",
                      }}
                    >
                      <span style={{ color: "var(--amber)" }}>
                        {c.confidenceTier}
                      </span>
                      {confidencePct !== null ? (
                        <span>· {confidencePct}%</span>
                      ) : null}
                      {c.topicHint ? <span>· {c.topicHint}</span> : null}
                      {c.attributedFounder ? (
                        <span>· {founderDisplayName(c.attributedFounder)}</span>
                      ) : null}
                    </div>
                    <p
                      style={{
                        margin: "0.3rem 0 0",
                        color: "var(--parchment)",
                        lineHeight: 1.45,
                        fontSize: "0.98rem",
                      }}
                    >
                      {c.text}
                    </p>
                  </Link>
                  {c.rationale ? (
                    <Excerpt
                      text={c.rationale}
                      lines={2}
                      style={{
                        marginTop: "0.3rem",
                        fontSize: "0.8rem",
                        color: "var(--parchment-dim)",
                        lineHeight: 1.5,
                      }}
                    />
                  ) : null}
                  {sourceUpload ? (
                    <div
                      className="mono"
                      style={{
                        marginTop: "0.4rem",
                        fontSize: "0.58rem",
                        color: "var(--parchment-dim)",
                        letterSpacing: "0.1em",
                        display: "flex",
                        gap: "0.4rem",
                        flexWrap: "wrap",
                      }}
                    >
                      <span style={{ textTransform: "uppercase" }}>
                        source
                      </span>
                      <Link
                        href={`/upload/${sourceUpload.id}`}
                        style={{ color: "var(--parchment)", textDecoration: "none" }}
                      >
                        {sourceUpload.title}
                      </Link>
                      {sourceUpload.sourceType ? (
                        <span>· {sourceUpload.sourceType}</span>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {display.length > 0 ? (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginTop: "1.25rem",
            padding: "0.75rem 0",
            borderTop: "1px solid var(--border)",
            flexWrap: "wrap",
            gap: "0.5rem",
          }}
        >
          <span style={{ fontSize: "0.7rem", color: "var(--parchment-dim)" }}>
            {total} conclusion{total !== 1 ? "s" : ""} · page {page}
          </span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            {page > 1 ? (
              <Link
                href={buildPageUrl(page - 1)}
                className="btn"
                style={{ fontSize: "0.62rem", padding: "0.3rem 0.65rem", textDecoration: "none" }}
              >
                ← Previous
              </Link>
            ) : null}
            {hasNext ? (
              <Link
                href={buildPageUrl(page + 1)}
                className="btn"
                style={{ fontSize: "0.62rem", padding: "0.3rem 0.65rem", textDecoration: "none" }}
              >
                Next →
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </main>
  );
}

export default async function ConclusionsPage({
  searchParams,
}: {
  searchParams: Promise<ConclusionsSearchParams>;
}) {
  return ConclusionsContent({ searchParams });
}
