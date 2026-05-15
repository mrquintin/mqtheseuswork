import "server-only";

import { db } from "@/lib/db";

import type {
  Lineage,
  LineageEdge,
  LineageNode,
  LineageNodeKind,
} from "@/lib/lineage";

/**
 * Server-only lineage assembler.
 *
 * Split out from `@/lib/lineage` so that client components (e.g.
 * `LineageTimeline`) can import the timeline types and pure projection
 * functions without dragging the Prisma + `pg` driver chain into the
 * browser bundle. `pg` requires Node built-ins (`fs`, `net`, `tls`,
 * `dns`) that webpack cannot resolve client-side; before the split the
 * Vercel build broke with `Module not found: Can't resolve 'fs'` etc.
 *
 * Anything in this file MUST stay on the server. The `server-only`
 * import above turns an accidental client import into a build-time
 * error rather than a runtime mystery.
 */

const KIND_PRIORITY: Record<LineageNodeKind, number> = {
  source: 0,
  claim: 1,
  methodology: 2,
  method_invocation: 3,
  conclusion: 4,
  peer_review: 5,
  drift: 6,
  revision: 7,
  calibration: 8,
  publication: 9,
  citation: 10,
};

function trunc(s: string | null | undefined, n: number): string {
  if (!s) return "";
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

function isoUtc(d: Date | string | null | undefined): string {
  if (!d) return new Date(0).toISOString();
  return (d instanceof Date ? d : new Date(d)).toISOString();
}

function tryParseStringArray(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function sortNodes(nodes: LineageNode[]): LineageNode[] {
  return [...nodes].sort((a, b) => {
    if (a.timestamp !== b.timestamp) return a.timestamp < b.timestamp ? -1 : 1;
    const pa = KIND_PRIORITY[a.kind];
    const pb = KIND_PRIORITY[b.kind];
    if (pa !== pb) return pa - pb;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
}

/**
 * Build the lineage for `conclusionId` within `organizationId`. Throws if
 * the conclusion doesn't exist or isn't in the org.
 *
 * The assembler is intentionally a single function with explicit reads
 * rather than a class hierarchy: the data model is denormalised JSON in
 * a few Prisma columns, and a flat function keeps the read path obvious.
 */
export async function assembleLineage(opts: {
  conclusionId: string;
  organizationId: string;
}): Promise<Lineage> {
  const { conclusionId, organizationId } = opts;

  const conclusion = await db.conclusion.findFirst({
    where: { id: conclusionId, organizationId },
    select: {
      id: true,
      text: true,
      rationale: true,
      confidence: true,
      confidenceTier: true,
      createdAt: true,
      updatedAt: true,
      evidenceChainClaimIds: true,
      dissentClaimIds: true,
      sources: {
        select: {
          createdAt: true,
          upload: {
            select: {
              id: true,
              title: true,
              authorBio: true,
              sourceType: true,
              slug: true,
              publishedAt: true,
              visibility: true,
              createdAt: true,
              founder: {
                select: { displayName: true, name: true, username: true },
              },
            },
          },
        },
      },
      methodologyProfiles: {
        select: {
          id: true,
          patternType: true,
          title: true,
          summary: true,
          confidence: true,
          createdAt: true,
        },
      },
      conclusionMethods: {
        select: {
          id: true,
          methodName: true,
          methodVersion: true,
          domain: true,
          weight: true,
          rationale: true,
          createdAt: true,
        },
      },
      publicationReviews: {
        select: {
          id: true,
          status: true,
          reviewerNotes: true,
          createdAt: true,
          updatedAt: true,
        },
      },
    },
  });

  if (!conclusion) {
    throw Object.assign(new Error("conclusion_not_found"), {
      status: 404,
    });
  }

  const nodes = new Map<string, LineageNode>();
  const edges: LineageEdge[] = [];
  const seenEdges = new Set<string>();
  const addEdge = (src: string, dst: string, relation: string) => {
    const key = `${src}␟${dst}␟${relation}`;
    if (seenEdges.has(key)) return;
    seenEdges.add(key);
    edges.push({ src, dst, relation });
  };

  const conclusionNid = `conclusion:${conclusion.id}`;
  nodes.set(conclusionNid, {
    id: conclusionNid,
    kind: "conclusion",
    label: trunc(conclusion.text, 120),
    timestamp: isoUtc(conclusion.createdAt),
    summary: trunc(conclusion.rationale, 480),
    payload: {
      confidence: conclusion.confidence,
      confidenceTier: conclusion.confidenceTier,
    },
    publicVisible: true,
    recordUrl: `/conclusions/${conclusion.id}`,
  });

  // Sources — public when the upload is published with org visibility.
  for (const cs of conclusion.sources) {
    const upload = cs.upload;
    if (!upload) continue;
    const nid = `source:${upload.id}`;
    const isPublic =
      upload.publishedAt !== null && upload.visibility === "org";
    nodes.set(nid, {
      id: nid,
      kind: "source",
      label: trunc(upload.title || upload.id, 120),
      timestamp: isoUtc(upload.publishedAt ?? upload.createdAt),
      summary: trunc(upload.authorBio || "", 480),
      payload: {
        uploadId: upload.id,
        slug: upload.slug,
        sourceType: upload.sourceType,
        publishedAt: upload.publishedAt
          ? isoUtc(upload.publishedAt)
          : null,
      },
      publicVisible: isPublic,
      recordUrl: upload.slug ? `/post/${upload.slug}` : `/library/${upload.id}`,
    });
    addEdge(nid, conclusionNid, "source_of");
  }

  // Claims listed on the conclusion payload. We don't have a Claim table
  // in Prisma — claim text lives in noosphere; here we surface only the
  // ids so the UI can render placeholders and clients can resolve them.
  for (const cid of tryParseStringArray(conclusion.evidenceChainClaimIds)) {
    const nid = `claim:${cid}`;
    if (nodes.has(nid)) {
      addEdge(nid, conclusionNid, "supports");
      continue;
    }
    nodes.set(nid, {
      id: nid,
      kind: "claim",
      label: `claim ${cid.slice(0, 12)}`,
      timestamp: isoUtc(conclusion.createdAt),
      summary: "",
      payload: { claimId: cid, role: "supports" },
      publicVisible: true,
      recordUrl: "",
    });
    addEdge(nid, conclusionNid, "supports");
  }
  for (const cid of tryParseStringArray(conclusion.dissentClaimIds)) {
    const nid = `claim:${cid}`;
    if (nodes.has(nid)) {
      addEdge(nid, conclusionNid, "dissents");
      continue;
    }
    nodes.set(nid, {
      id: nid,
      kind: "claim",
      label: `claim ${cid.slice(0, 12)}`,
      timestamp: isoUtc(conclusion.createdAt),
      summary: "",
      payload: { claimId: cid, role: "dissents" },
      publicVisible: true,
      recordUrl: "",
    });
    addEdge(nid, conclusionNid, "dissents");
  }

  // Methodology profiles. Public when an upload bridge published them or
  // when the conclusion itself has a published PublicationReview; the
  // simple rule we adopt: publish iff the conclusion has a published
  // review. That keeps the public lineage in sync with the public post.
  const hasPublishedReview = conclusion.publicationReviews.some(
    (r) => r.status === "published",
  );
  for (const mp of conclusion.methodologyProfiles) {
    const nid = `methodology:${mp.id}`;
    nodes.set(nid, {
      id: nid,
      kind: "methodology",
      label: trunc(mp.title || mp.patternType || "methodology", 120),
      timestamp: isoUtc(mp.createdAt),
      summary: trunc(mp.summary, 480),
      payload: {
        patternType: mp.patternType,
        confidence: mp.confidence,
      },
      publicVisible: hasPublishedReview,
      recordUrl: `/conclusions/${conclusion.id}?tab=provenance`,
    });
    addEdge(nid, conclusionNid, "describes");
  }

  // Method invocations (ConclusionMethod links — registry methods).
  for (const cm of conclusion.conclusionMethods) {
    const nid = `method:${cm.id}`;
    nodes.set(nid, {
      id: nid,
      kind: "method_invocation",
      label: `${cm.methodName}@${cm.methodVersion}`,
      timestamp: isoUtc(cm.createdAt),
      summary: trunc(cm.rationale, 480),
      payload: {
        methodName: cm.methodName,
        methodVersion: cm.methodVersion,
        domain: cm.domain,
        weight: cm.weight,
      },
      publicVisible: hasPublishedReview,
      recordUrl: `/methods/${cm.methodName}/${cm.methodVersion}`,
    });
    addEdge(nid, conclusionNid, "produced");
  }

  // Publication reviews (private) and the resulting public publications.
  for (const pr of conclusion.publicationReviews) {
    const nid = `pubreview:${pr.id}`;
    nodes.set(nid, {
      id: nid,
      kind: "peer_review",
      label: `publication review: ${pr.status}`,
      timestamp: isoUtc(pr.updatedAt ?? pr.createdAt),
      summary: trunc(pr.reviewerNotes, 480),
      payload: { status: pr.status },
      publicVisible: false,
      recordUrl: `/conclusions/${conclusion.id}?tab=peer`,
    });
    addEdge(nid, conclusionNid, "gates");
  }

  // PublishedConclusion snapshots — these ARE the public-visible lineage
  // anchor; one per material revision.
  const publications = await db.publishedConclusion.findMany({
    where: { organizationId, sourceConclusionId: conclusion.id },
    select: {
      id: true,
      slug: true,
      version: true,
      publishedAt: true,
      doi: true,
      kind: true,
      discountedConfidence: true,
    },
    orderBy: { publishedAt: "asc" },
  });
  for (const p of publications) {
    const nid = `publication:${p.id}`;
    nodes.set(nid, {
      id: nid,
      kind: "publication",
      label: `published v${p.version}${p.doi ? ` · ${p.doi}` : ""}`,
      timestamp: isoUtc(p.publishedAt),
      summary: "",
      payload: {
        slug: p.slug,
        version: p.version,
        doi: p.doi,
        kind: p.kind,
        discountedConfidence: p.discountedConfidence,
      },
      publicVisible: true,
      recordUrl: `/c/${p.slug}/v/${p.version}`,
    });
    addEdge(conclusionNid, nid, "published_as");
  }

  // Drift events targeting this conclusion (private — internal calibration).
  const drifts = await db.driftEvent.findMany({
    where: { organizationId, targetId: conclusion.id },
    select: {
      id: true,
      observedAt: true,
      driftScore: true,
      severity: true,
      naturalLanguageSummary: true,
      notes: true,
    },
    orderBy: { observedAt: "asc" },
  });
  for (const d of drifts) {
    const nid = `drift:${d.id}`;
    nodes.set(nid, {
      id: nid,
      kind: "drift",
      label: `drift ${d.driftScore.toFixed(2)}${d.severity ? ` · ${d.severity}` : ""}`,
      timestamp: isoUtc(d.observedAt),
      summary: trunc(d.naturalLanguageSummary || d.notes, 480),
      payload: {
        driftScore: d.driftScore,
        severity: d.severity,
      },
      publicVisible: false,
      recordUrl: "",
    });
    addEdge(nid, conclusionNid, "observed_on");
  }

  // Revision events that touched this conclusion (private).
  const revisions = await db.revisionEvent.findMany({
    where: {
      organizationId,
      affectedConclusionIds: { contains: conclusion.id },
    },
    select: {
      id: true,
      planId: true,
      createdAt: true,
      revertedAt: true,
      preConfidenceSnapshot: true,
    },
    orderBy: { createdAt: "asc" },
  });
  for (const rv of revisions) {
    let confidenceBefore: number | null = null;
    try {
      const snap = JSON.parse(rv.preConfidenceSnapshot) as Record<
        string,
        number
      >;
      if (typeof snap[conclusion.id] === "number") {
        confidenceBefore = snap[conclusion.id];
      }
    } catch {
      // Malformed snapshot — surface the row anyway so the timeline
      // still shows the revision happened.
    }
    const nid = `revision:${rv.id}`;
    nodes.set(nid, {
      id: nid,
      kind: "revision",
      label: rv.revertedAt ? "revision (reverted)" : "revision",
      timestamp: isoUtc(rv.createdAt),
      summary:
        confidenceBefore !== null
          ? `confidence before: ${confidenceBefore.toFixed(3)}`
          : "",
      payload: {
        planId: rv.planId,
        revertedAt: rv.revertedAt ? isoUtc(rv.revertedAt) : null,
        confidenceBefore,
      },
      publicVisible: false,
      recordUrl: `/revisions/${rv.id}`,
    });
    addEdge(nid, conclusionNid, "revises");
  }

  return {
    conclusionId: conclusion.id,
    assembledAt: new Date().toISOString(),
    nodes: sortNodes([...nodes.values()]),
    edges,
  };
}
