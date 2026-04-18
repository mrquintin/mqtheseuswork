import Link from "next/link";
import { Suspense } from "react";
import TemporalReplayBar from "@/components/TemporalReplayBar";
import ConfidenceTierSigil from "@/components/ConfidenceTierSigil";
import SculptureAscii from "@/components/SculptureAsciiClient";
import { db } from "@/lib/db";
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

export default async function ConclusionsPage({
  searchParams,
}: {
  searchParams: Promise<{ tier?: string; topic?: string; asOf?: string }>;
}) {
  const sp = await searchParams;
  const asOf = sp.asOf;
  const replay = Boolean(asOf && AS_OF_ISO.test(asOf));

  if (replay) {
    const { rows, error } = await fetchReplayConclusions(asOf!);
    return (
      <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
        <Suspense fallback={null}>
          <TemporalReplayBar />
        </Suspense>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.12em",
            textShadow: "var(--glow-sm)",
          }}
        >
          Conclusiones
        </h1>
        <p
          style={{
            color: "var(--ember)",
            fontSize: "0.85rem",
            marginBottom: "1rem",
          }}
        >
          Replay mode: conclusions consistent with Noosphere evidence as of{" "}
          <strong>{asOf}</strong> (see Operations manual for imperfections).
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
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
          }}
        >
          {rows.map((c) => (
            <li
              key={c.id}
              className="portal-card"
              style={{ padding: "1rem 1.25rem", display: "flex", gap: "0.9rem" }}
            >
              <ConfidenceTierSigil tier={c.confidence_tier || "open"} />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div
                  className="mono"
                  style={{
                    fontSize: "0.62rem",
                    color: "var(--amber-dim)",
                    textTransform: "uppercase",
                    letterSpacing: "0.12em",
                  }}
                >
                  {c.confidence_tier || ""}
                  {c.created_at
                    ? ` · recorded ${String(c.created_at).slice(0, 10)}`
                    : ""}
                </div>
                <p style={{ marginTop: "0.45rem", color: "var(--parchment)" }}>
                  {c.text}
                </p>
                {c.rationale ? (
                  <p
                    style={{
                      marginTop: "0.35rem",
                      fontSize: "0.8rem",
                      color: "var(--parchment-dim)",
                    }}
                  >
                    {c.rationale}
                  </p>
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

  const where: {
    organizationId: string;
    confidenceTier?: string;
    topicHint?: { contains: string };
  } = { organizationId: tenant.organizationId };
  if (sp.tier) where.confidenceTier = sp.tier;
  if (sp.topic) where.topicHint = { contains: sp.topic };

  const rows = await db.conclusion.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 80,
    include: { attributedFounder: { select: { name: true } } },
  });

  return (
    <main style={{ padding: "2rem 0" }}>
      <div style={{ maxWidth: "960px", margin: "0 auto", padding: "0 2rem" }}>
        <Suspense fallback={null}>
          <TemporalReplayBar />
        </Suspense>

        {/* Doryphoros — "the spear-bearer", Polykleitos' canonical figure.
            Stands at the head of the Conclusions list because it is
            literally the canon: the figure by which proportions are
            measured. The firm's conclusions are its own canon. */}
        <section
          aria-hidden="true"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "2rem",
            flexWrap: "wrap",
            margin: "0.5rem 0 2rem",
          }}
        >
          <SculptureAscii
            src="/sculptures/doryphoros.mesh.bin"
            cols={34}
            rows={22}
            yawSpeed={0.025}
            pitch={-0.1}
            ariaLabel="Doryphoros — the spear-bearer, canon of proportion"
          />
          <div style={{ maxWidth: "340px" }}>
            <h1
              style={{
                fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
                fontSize: "1.8rem",
                letterSpacing: "0.18em",
                color: "var(--amber)",
                textShadow: "var(--glow-sm)",
                margin: 0,
              }}
            >
              Conclusiones
            </h1>
            <p
              className="mono"
              style={{
                fontSize: "0.62rem",
                letterSpacing: "0.28em",
                textTransform: "uppercase",
                color: "var(--amber-dim)",
                margin: "0.25rem 0 0",
              }}
            >
              The firm&apos;s canon · Doryphoros, MIA
            </p>
            <p
              style={{
                fontFamily: "'EB Garamond', serif",
                fontStyle: "italic",
                fontSize: "0.95rem",
                color: "var(--parchment-dim)",
                marginTop: "0.5rem",
                marginBottom: 0,
                lineHeight: 1.55,
              }}
            >
              Polykleitos made the figure by which all other figures are
              measured. A conclusion the firm stands behind is the same kind
              of object.
            </p>
          </div>
        </section>

        <p
          className="mono"
          style={{
            color: "var(--amber-dim)",
            marginBottom: "0.75rem",
            fontSize: "0.62rem",
            letterSpacing: "0.2em",
            textTransform: "uppercase",
          }}
        >
          Filtra · Quick filters
        </p>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.5rem",
            marginBottom: "1.75rem",
            alignItems: "center",
          }}
        >
          <Link
            href="/conclusions"
            className="btn"
            style={{ fontSize: "0.7rem", textDecoration: "none" }}
          >
            All
          </Link>
          {TIERS.map((t) => (
            <Link
              key={t}
              href={`/conclusions?tier=${t}`}
              className="btn"
              style={{
                fontSize: "0.7rem",
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                // Slight emphasis on the active filter.
                ...(sp.tier === t
                  ? {
                      borderColor: "var(--amber)",
                      color: "var(--amber)",
                    }
                  : {}),
              }}
            >
              <ConfidenceTierSigil tier={t} size="0.55rem" />
              <span>{t}</span>
            </Link>
          ))}
          <Link
            href="/conclusions?topic=method"
            className="btn"
            style={{ fontSize: "0.7rem", textDecoration: "none" }}
          >
            topic: method
          </Link>
        </div>

        {rows.length === 0 ? (
          <div
            className="ascii-frame"
            data-label="VACUUM · EMPTY"
            style={{ padding: "2rem 1rem", textAlign: "center" }}
          >
            <p
              style={{
                fontFamily: "'EB Garamond', serif",
                fontStyle: "italic",
                fontSize: "1.1rem",
                color: "var(--parchment)",
                margin: 0,
              }}
            >
              Nihil adhuc conclusum.
            </p>
            <p
              className="mono"
              style={{
                fontSize: "0.7rem",
                color: "var(--parchment-dim)",
                marginTop: "0.4rem",
              }}
            >
              No conclusions yet — nothing for the firm to stand behind.
            </p>
          </div>
        ) : (
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.75rem",
            }}
          >
            {rows.map((c) => (
              <li
                key={c.id}
                className="portal-card"
                style={{ padding: "1rem 1.25rem" }}
              >
                <Link
                  href={`/conclusions/${c.id}`}
                  style={{
                    textDecoration: "none",
                    color: "inherit",
                    display: "flex",
                    gap: "0.9rem",
                    alignItems: "flex-start",
                  }}
                >
                  <ConfidenceTierSigil tier={c.confidenceTier} />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div
                      className="mono"
                      style={{
                        fontSize: "0.62rem",
                        color: "var(--amber-dim)",
                        textTransform: "uppercase",
                        letterSpacing: "0.12em",
                      }}
                    >
                      {c.confidenceTier}
                      {c.topicHint ? ` · ${c.topicHint}` : ""}
                      {c.attributedFounder
                        ? ` · ${c.attributedFounder.name}`
                        : ""}
                    </div>
                    <p
                      style={{
                        marginTop: "0.5rem",
                        color: "var(--parchment)",
                      }}
                    >
                      {c.text}
                    </p>
                    {c.rationale && (
                      <p
                        style={{
                          marginTop: "0.35rem",
                          fontSize: "0.8rem",
                          color: "var(--parchment-dim)",
                        }}
                      >
                        {c.rationale}
                      </p>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
