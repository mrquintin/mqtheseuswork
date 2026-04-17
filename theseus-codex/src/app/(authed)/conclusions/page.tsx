import Link from "next/link";
import { Suspense } from "react";
import TemporalReplayBar from "@/components/TemporalReplayBar";
import { db } from "@/lib/db";
import { fetchReplayConclusions } from "@/lib/noosphereReplayBridge";
import { AS_OF_ISO } from "@/lib/replayDate";
import { requireTenantContext } from "@/lib/tenant";

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
        <h1 style={{ fontFamily: "'Cinzel', serif", color: "var(--gold)", letterSpacing: "0.08em" }}>
          Conclusions
        </h1>
        <p style={{ color: "var(--ember)", fontSize: "0.85rem", marginBottom: "1rem" }}>
          Replay mode: conclusions consistent with Noosphere evidence as of{" "}
          <strong>{asOf}</strong> (see Operations manual for imperfections).
        </p>
        {error ? (
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem" }}>{error}</p>
        ) : null}
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {rows.map((c) => (
            <li key={c.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
              <div style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
                {c.confidence_tier || ""}
                {c.created_at ? ` · recorded ${String(c.created_at).slice(0, 10)}` : ""}
              </div>
              <p style={{ marginTop: "0.5rem", color: "var(--parchment)" }}>{c.text}</p>
              {c.rationale ? (
                <p style={{ marginTop: "0.35rem", fontSize: "0.8rem", color: "var(--parchment-dim)" }}>{c.rationale}</p>
              ) : null}
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
      <p style={{ color: "var(--parchment-dim)", marginBottom: "0.75rem", fontSize: "0.9rem" }}>
        Quick filters:
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <Link href="/conclusions" className="btn" style={{ fontSize: "0.65rem", textDecoration: "none" }}>
          All
        </Link>
        {["firm", "founder", "open"].map((t) => (
          <Link
            key={t}
            href={`/conclusions?tier=${t}`}
            className="btn"
            style={{ fontSize: "0.65rem", textDecoration: "none" }}
          >
            {t}
          </Link>
        ))}
        <Link
          href="/conclusions?topic=method"
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          topic: method
        </Link>
      </div>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {rows.map((c) => (
          <li key={c.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
            <Link
              href={`/conclusions/${c.id}`}
              style={{ textDecoration: "none", color: "inherit", display: "block" }}
            >
              <div style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
                {c.confidenceTier}
                {c.topicHint ? ` · ${c.topicHint}` : ""}
                {c.attributedFounder ? ` · ${c.attributedFounder.name}` : ""}
              </div>
              <p style={{ marginTop: "0.5rem", color: "var(--parchment)" }}>{c.text}</p>
              {c.rationale && (
                <p style={{ marginTop: "0.35rem", fontSize: "0.8rem", color: "var(--parchment-dim)" }}>{c.rationale}</p>
              )}
            </Link>
          </li>
        ))}
      </ul>
      </div>
    </main>
  );
}
