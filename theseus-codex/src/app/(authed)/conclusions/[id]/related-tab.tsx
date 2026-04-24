import Link from "next/link";
import ConfidenceTierSigil from "@/components/ConfidenceTierSigil";
import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

type RelatedConclusion = {
  id: string;
  text: string;
  confidenceTier: string;
  confidence: number;
};

function parseIdArray(raw: string): string[] {
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
}

/**
 * Related-conclusions tab. Two relationship types are surfaced:
 *
 *  1. "From the same sources" — resolved via `ConclusionSource`, which
 *     is the upload↔conclusion bridge. If two conclusions were extracted
 *     from any overlapping upload they show up here.
 *
 *  2. "Sharing supporting principles / evidence / dissent" — the
 *     `supportingPrincipleIds` / `evidenceChainClaimIds` / `dissentClaimIds`
 *     fields are JSON strings. We scan the full-tenant conclusion set
 *     and flag any row whose parsed array overlaps this conclusion's.
 *     This is a linear scan rather than a SQL JSON query because Prisma
 *     stores these as plain strings — acceptable at the tens-of-
 *     thousands conclusion scale this tool operates at.
 */
export default async function RelatedTab({
  conclusionId,
}: {
  conclusionId: string;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const current = await db.conclusion.findFirst({
    where: { id: conclusionId, organizationId: tenant.organizationId },
    select: {
      supportingPrincipleIds: true,
      evidenceChainClaimIds: true,
      dissentClaimIds: true,
    },
  });
  if (!current) return null;

  const supportSet = new Set(parseIdArray(current.supportingPrincipleIds));
  const evidenceSet = new Set(parseIdArray(current.evidenceChainClaimIds));
  const dissentSet = new Set(parseIdArray(current.dissentClaimIds));

  // Method A — shared source uploads
  const sources = await db.conclusionSource.findMany({
    where: { conclusionId },
    select: { uploadId: true },
  });
  const uploadIds = sources.map((s) => s.uploadId);

  let sharedSourceConclusions: RelatedConclusion[] = [];
  if (uploadIds.length > 0) {
    const rows = await db.conclusionSource.findMany({
      where: {
        uploadId: { in: uploadIds },
        conclusionId: { not: conclusionId },
        conclusion: { organizationId: tenant.organizationId },
      },
      include: {
        conclusion: {
          select: { id: true, text: true, confidenceTier: true, confidence: true },
        },
      },
      take: 60,
    });
    const seen = new Set<string>();
    for (const r of rows) {
      if (seen.has(r.conclusion.id)) continue;
      seen.add(r.conclusion.id);
      sharedSourceConclusions.push(r.conclusion);
      if (sharedSourceConclusions.length >= 20) break;
    }
  }

  // Method B — shared principle/evidence/dissent IDs
  let sharedPrincipleConclusions: RelatedConclusion[] = [];
  if (supportSet.size + evidenceSet.size + dissentSet.size > 0) {
    const candidates = await db.conclusion.findMany({
      where: {
        organizationId: tenant.organizationId,
        id: { not: conclusionId },
      },
      select: {
        id: true,
        text: true,
        confidenceTier: true,
        confidence: true,
        supportingPrincipleIds: true,
        evidenceChainClaimIds: true,
        dissentClaimIds: true,
      },
      take: 200,
    });
    for (const c of candidates) {
      const overlap =
        parseIdArray(c.supportingPrincipleIds).some((id) => supportSet.has(id)) ||
        parseIdArray(c.evidenceChainClaimIds).some((id) => evidenceSet.has(id)) ||
        parseIdArray(c.dissentClaimIds).some((id) => dissentSet.has(id));
      if (overlap) {
        sharedPrincipleConclusions.push({
          id: c.id,
          text: c.text,
          confidenceTier: c.confidenceTier,
          confidence: c.confidence,
        });
        if (sharedPrincipleConclusions.length >= 20) break;
      }
    }
  }

  if (sharedSourceConclusions.length === 0 && sharedPrincipleConclusions.length === 0) {
    return (
      <div style={{ padding: "0.75rem 0", color: "var(--parchment-dim)", fontSize: "0.85rem" }}>
        No related conclusions found.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {sharedSourceConclusions.length > 0 && (
        <RelatedSection
          label="From the same sources"
          conclusions={sharedSourceConclusions}
        />
      )}
      {sharedPrincipleConclusions.length > 0 && (
        <RelatedSection
          label="Sharing principles / evidence / dissent"
          conclusions={sharedPrincipleConclusions}
        />
      )}
    </div>
  );
}

function RelatedSection({
  label,
  conclusions,
}: {
  label: string;
  conclusions: RelatedConclusion[];
}) {
  return (
    <div>
      <h4
        style={{
          fontFamily: "'Cinzel', serif",
          fontSize: "0.65rem",
          letterSpacing: "0.15em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
          margin: "0 0 0.5rem",
        }}
      >
        {label}
      </h4>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
        {conclusions.map((c) => (
          <Link
            key={c.id}
            href={`/conclusions/${c.id}`}
            style={{
              display: "flex",
              gap: "0.6rem",
              alignItems: "flex-start",
              padding: "0.5rem 0.75rem",
              borderLeft: "2px solid var(--gold-dim)",
              textDecoration: "none",
              color: "var(--parchment)",
            }}
          >
            <ConfidenceTierSigil tier={c.confidenceTier} size="0.55rem" />
            <span style={{ fontSize: "0.85rem", lineHeight: 1.45 }}>
              {c.text.slice(0, 160)}
              {c.text.length > 160 ? "…" : ""}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
