/**
 * Lineage — types and a Prisma-backed assembler shared between the
 * founder and public API routes.
 *
 * The shape mirrors `noosphere.temporal.lineage.Lineage` so the same JSON
 * is interpretable on either side. The TS assembler reads from Prisma
 * (the source of truth for founder-side rows) rather than re-implementing
 * the cascade-graph walk; the Python assembler covers the synthesis side
 * from the noosphere `Store`.
 *
 * Public visibility rule: each node carries a `publicVisible` boolean.
 * `filterPublic()` drops private nodes AND any edge that touches one,
 * leaving no redaction stub. A reader of the public lineage cannot tell
 * private steps exist.
 */

import { db } from "@/lib/db";

export type LineageNodeKind =
  | "source"
  | "claim"
  | "methodology"
  | "method_invocation"
  | "peer_review"
  | "revision"
  | "drift"
  | "calibration"
  | "conclusion"
  | "publication"
  | "citation";

export type LineageNode = {
  id: string;
  kind: LineageNodeKind;
  label: string;
  /** ISO-8601 UTC. */
  timestamp: string;
  summary: string;
  payload: Record<string, unknown>;
  publicVisible: boolean;
  recordUrl: string;
};

export type LineageEdge = {
  src: string;
  dst: string;
  relation: string;
};

export type Lineage = {
  conclusionId: string;
  /** ISO-8601 UTC. */
  assembledAt: string;
  nodes: LineageNode[];
  edges: LineageEdge[];
};

export type LineageDiff = {
  added: LineageNode[];
  removed: LineageNode[];
  changed: { id: string; before: LineageNode; after: LineageNode }[];
};

// Causal ordering for ties on timestamp. Must match `_KIND_PRIORITY` in
// the Python assembler so the JSON is byte-stable across implementations.
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

/** Filter a lineage to only the nodes a public reader is allowed to see. */
export function filterPublic(lineage: Lineage): Lineage {
  const keep = new Set<string>();
  for (const n of lineage.nodes) if (n.publicVisible) keep.add(n.id);
  return {
    conclusionId: lineage.conclusionId,
    assembledAt: lineage.assembledAt,
    nodes: lineage.nodes.filter((n) => keep.has(n.id)),
    edges: lineage.edges.filter((e) => keep.has(e.src) && keep.has(e.dst)),
  };
}

/** Two-snapshot diff — used by revision-event "what changed" rendering. */
export function lineageDiff(before: Lineage, after: Lineage): LineageDiff {
  const a = new Map(before.nodes.map((n) => [n.id, n] as const));
  const b = new Map(after.nodes.map((n) => [n.id, n] as const));
  const added: LineageNode[] = [];
  const removed: LineageNode[] = [];
  const changed: LineageDiff["changed"] = [];
  for (const [id, node] of b) if (!a.has(id)) added.push(node);
  for (const [id, node] of a) if (!b.has(id)) removed.push(node);
  for (const [id, av] of a) {
    const bv = b.get(id);
    if (!bv) continue;
    if (JSON.stringify(av) !== JSON.stringify(bv)) {
      changed.push({ id, before: av, after: bv });
    }
  }
  return { added, removed, changed };
}

// ════════════════════════════════════════════════════════════════════
// Layered timeline model (v2 rendering refactor — Round 17 prompt 17 v2)
//
// v1 rendered the lineage as one flat <ol>. For a real conclusion with
// 30+ events that is unreadable, so v2 reorganises the *same* `Lineage`
// data shape into horizontal swim lanes (one column per phase) with
// vertical position encoding time. Nothing in the assembler above
// changes; everything below is a pure, side-effect-free projection that
// the React timeline (and its tests) drive.
// ════════════════════════════════════════════════════════════════════

export type LineageLaneId =
  | "source-ingestion"
  | "extraction"
  | "methodology"
  | "review"
  | "revision"
  | "publication"
  | "outcomes";

/** Lane columns, left → right, in causal phase order. */
export const LINEAGE_LANES: ReadonlyArray<{ id: LineageLaneId; label: string }> =
  [
    { id: "source-ingestion", label: "Source ingestion" },
    { id: "extraction", label: "Extraction" },
    { id: "methodology", label: "Methodology" },
    { id: "review", label: "Review" },
    { id: "revision", label: "Revision" },
    { id: "publication", label: "Publication" },
    { id: "outcomes", label: "Outcomes" },
  ];

const KIND_TO_LANE: Record<LineageNodeKind, LineageLaneId> = {
  source: "source-ingestion",
  claim: "extraction",
  methodology: "methodology",
  method_invocation: "methodology",
  peer_review: "review",
  drift: "review",
  calibration: "revision",
  revision: "revision",
  conclusion: "publication",
  publication: "publication",
  citation: "outcomes",
};

export function laneForKind(kind: LineageNodeKind): LineageLaneId {
  return KIND_TO_LANE[kind] ?? "outcomes";
}

export const LINEAGE_KIND_LABELS: Record<LineageNodeKind, string> = {
  source: "Source",
  claim: "Claim",
  methodology: "Methodology",
  method_invocation: "Method",
  conclusion: "Conclusion",
  peer_review: "Review",
  drift: "Drift",
  revision: "Revision",
  calibration: "Calibration",
  publication: "Publication",
  citation: "Citation",
};

export const LINEAGE_KIND_COLORS: Record<LineageNodeKind, string> = {
  source: "var(--parchment-dim)",
  claim: "var(--amber-dim)",
  methodology: "var(--amber)",
  method_invocation: "var(--amber)",
  conclusion: "var(--gold)",
  peer_review: "var(--parchment)",
  drift: "var(--ember)",
  revision: "var(--ember)",
  calibration: "var(--parchment-dim)",
  publication: "var(--gold)",
  citation: "var(--parchment-dim)",
};

/** A lineage with more events than this is "long": source-ingestion is
 *  collapsed by default so the reader is not buried in ingestion noise. */
export const LINEAGE_LONG_THRESHOLD = 30;

/** Initial / per-page event count for the virtualised timeline. */
export const LINEAGE_PAGE_SIZE = 100;

/** Default scroll-viewport height (px) used before the DOM measures it. */
export const LINEAGE_VIEWPORT_HEIGHT = 560;

/**
 * Default lane checkbox state. methodology / review / revision /
 * outcomes are always on; publication carries the conclusion node so it
 * is always on; extraction is on; source-ingestion is collapsed by
 * default once the lineage is "long".
 */
export function defaultLaneVisibility(
  nodeCount: number,
): Record<LineageLaneId, boolean> {
  const long = nodeCount > LINEAGE_LONG_THRESHOLD;
  return {
    "source-ingestion": !long,
    extraction: true,
    methodology: true,
    review: true,
    revision: true,
    publication: true,
    outcomes: true,
  };
}

function nodeMs(n: LineageNode): number {
  const t = Date.parse(n.timestamp);
  return Number.isNaN(t) ? 0 : t;
}

export function lineageTimeExtent(
  nodes: ReadonlyArray<LineageNode>,
): { min: number; max: number } {
  if (nodes.length === 0) return { min: 0, max: 0 };
  let min = Infinity;
  let max = -Infinity;
  for (const n of nodes) {
    const t = nodeMs(n);
    if (t < min) min = t;
    if (t > max) max = t;
  }
  return { min, max };
}

// ── Event grouping ──────────────────────────────────────────────────-

/** Adjacent same-lane events within this window collapse into a pill. */
export const LINEAGE_GROUP_WINDOW_MS = 60 * 60 * 1000; // one hour
/** A run shorter than this stays as individual cards. */
export const LINEAGE_GROUP_MIN_SIZE = 3;

export type LineageTimelineItem =
  | {
      type: "event";
      id: string;
      lane: LineageLaneId;
      timestamp: number;
      node: LineageNode;
    }
  | {
      type: "group";
      id: string;
      lane: LineageLaneId;
      timestamp: number; // representative position (newest member)
      startMs: number;
      endMs: number;
      nodes: LineageNode[];
    };

/**
 * Collapse runs of adjacent same-lane events that all fall within
 * `windowMs` of the run's first event into one group item. A run
 * shorter than `minGroupSize` is emitted as individual events.
 *
 * `laneNodes` must already be sorted ascending by timestamp.
 */
export function groupLaneEvents(
  laneNodes: ReadonlyArray<LineageNode>,
  lane: LineageLaneId,
  windowMs: number = LINEAGE_GROUP_WINDOW_MS,
  minGroupSize: number = LINEAGE_GROUP_MIN_SIZE,
): LineageTimelineItem[] {
  const out: LineageTimelineItem[] = [];
  let run: LineageNode[] = [];
  let runStart = 0;

  const flush = () => {
    if (run.length === 0) return;
    if (run.length >= minGroupSize) {
      const startMs = nodeMs(run[0]);
      const endMs = nodeMs(run[run.length - 1]);
      out.push({
        type: "group",
        id: `group:${lane}:${run[0].id}:${run[run.length - 1].id}`,
        lane,
        timestamp: endMs,
        startMs,
        endMs,
        nodes: run,
      });
    } else {
      for (const n of run) {
        out.push({
          type: "event",
          id: n.id,
          lane,
          timestamp: nodeMs(n),
          node: n,
        });
      }
    }
    run = [];
  };

  for (const n of laneNodes) {
    const t = nodeMs(n);
    if (run.length === 0) {
      run = [n];
      runStart = t;
    } else if (t - runStart <= windowMs) {
      run.push(n);
    } else {
      flush();
      run = [n];
      runStart = t;
    }
  }
  flush();
  return out;
}

// ── Layout + virtualisation ─────────────────────────────────────────-

export interface LineageTimelineLayout {
  cardHeight: number;
  cardGap: number;
  /** px the full time extent maps onto. 0 ⇒ derived from densest lane. */
  timeAxisHeight: number;
}

export const DEFAULT_LINEAGE_LAYOUT: LineageTimelineLayout = {
  cardHeight: 58,
  cardGap: 10,
  timeAxisHeight: 0,
};

export interface PositionedLineageItem {
  item: LineageTimelineItem;
  lane: LineageLaneId;
  laneIndex: number;
  /** top offset (px) within the lane body. Newest sits at y = 0. */
  y: number;
  height: number;
}

export interface LineageLaneModel {
  id: LineageLaneId;
  label: string;
  index: number;
  visible: boolean;
  /** events (pre-grouping) assigned to this lane in the current page +
   *  time window — reported in the toolbar even when the lane is off. */
  eventCount: number;
  items: PositionedLineageItem[];
}

export interface LineageTimelineModel {
  lanes: LineageLaneModel[];
  /** positioned items across *visible* lanes, sorted top→bottom (y asc). */
  flatItems: PositionedLineageItem[];
  totalHeight: number;
  timeExtent: { min: number; max: number };
  /** events (not groups) across all lanes in the current page + window. */
  totalEvents: number;
  /** events in *visible* lanes only. */
  shownEvents: number;
  /** events available in the full lineage before pagination. */
  availableEvents: number;
}

export interface ComputeLineageTimelineOptions {
  visibleLanes: Partial<Record<LineageLaneId, boolean>>;
  /** [startMs, endMs] inclusive. null/undefined ⇒ full extent. */
  timeRange?: [number, number] | null;
  /** pagination: include only the N most-recent events. */
  visibleCount?: number;
  groupWindowMs?: number;
  groupMinSize?: number;
  layout?: Partial<LineageTimelineLayout>;
}

/**
 * Project a node list into the layered, positioned timeline model.
 *
 * Pure and cheap (O(n log n) for the sort, O(n) for the rest) so it can
 * run on every lane toggle / time-range change without a frame budget
 * concern; the per-scroll-frame cost lives in `virtualizeLineageItems`.
 */
export function computeLineageTimeline(
  nodes: ReadonlyArray<LineageNode>,
  opts: ComputeLineageTimelineOptions,
): LineageTimelineModel {
  const layout = { ...DEFAULT_LINEAGE_LAYOUT, ...(opts.layout ?? {}) };
  const slot = layout.cardHeight + layout.cardGap;
  const visibleCount = opts.visibleCount ?? LINEAGE_PAGE_SIZE;
  const range = opts.timeRange ?? null;

  // 1. Sort ascending by time (input is usually already sorted).
  const sorted = [...nodes].sort((a, b) => nodeMs(a) - nodeMs(b));
  const availableEvents = sorted.length;

  // 2. Time-range filter.
  const inRange = range
    ? sorted.filter((n) => {
        const t = nodeMs(n);
        return t >= range[0] && t <= range[1];
      })
    : sorted;

  // 3. Pagination — keep only the `visibleCount` most-recent events.
  const paged =
    inRange.length > visibleCount
      ? inRange.slice(inRange.length - visibleCount)
      : inRange;

  const timeExtent = lineageTimeExtent(paged);
  const span = timeExtent.max - timeExtent.min;

  // 4. Bucket into lanes.
  const laneNodes = new Map<LineageLaneId, LineageNode[]>();
  for (const lane of LINEAGE_LANES) laneNodes.set(lane.id, []);
  for (const n of paged) laneNodes.get(laneForKind(n.kind))!.push(n);

  // The densest lane drives the time-axis height: it stacks with no
  // overlap, and sparser lanes spread out along the same axis by time.
  let maxLaneCount = 0;
  for (const arr of laneNodes.values()) {
    if (arr.length > maxLaneCount) maxLaneCount = arr.length;
  }
  const timeAxisHeight =
    layout.timeAxisHeight > 0
      ? layout.timeAxisHeight
      : Math.max(slot, maxLaneCount * slot);

  // 5. Group + position per lane. Newest at top (y = 0); y grows
  //    downward = older. A minimum gap prevents cards from overlapping
  //    when their timestamps are near-identical.
  const lanes: LineageLaneModel[] = [];
  let totalHeight = layout.cardHeight;
  let totalEvents = 0;
  let shownEvents = 0;

  LINEAGE_LANES.forEach((laneDef, laneIndex) => {
    const arr = laneNodes.get(laneDef.id)!;
    totalEvents += arr.length;
    const visible = opts.visibleLanes[laneDef.id] ?? false;
    const grouped = groupLaneEvents(
      arr,
      laneDef.id,
      opts.groupWindowMs,
      opts.groupMinSize,
    );
    // Position newest-first so the min-gap pushes *older* cards down.
    const desc = [...grouped].sort((a, b) => b.timestamp - a.timestamp);
    const positioned: PositionedLineageItem[] = [];
    let prevBottom = 0;
    for (const it of desc) {
      const timeY =
        span > 0
          ? ((timeExtent.max - it.timestamp) / span) * timeAxisHeight
          : prevBottom;
      const y = Math.max(timeY, prevBottom);
      positioned.push({
        item: it,
        lane: laneDef.id,
        laneIndex,
        y,
        height: layout.cardHeight,
      });
      prevBottom = y + layout.cardHeight + layout.cardGap;
    }
    if (visible) {
      shownEvents += arr.length;
      if (prevBottom > totalHeight) totalHeight = prevBottom;
    }
    lanes.push({
      id: laneDef.id,
      label: laneDef.label,
      index: laneIndex,
      visible,
      eventCount: arr.length,
      items: positioned,
    });
  });

  const flatItems = lanes
    .filter((l) => l.visible)
    .flatMap((l) => l.items)
    .sort((a, b) => a.y - b.y || a.laneIndex - b.laneIndex);

  return {
    lanes,
    flatItems,
    totalHeight,
    timeExtent,
    totalEvents,
    shownEvents,
    availableEvents,
  };
}

export interface VirtualLineageWindow {
  start: number;
  end: number;
  items: PositionedLineageItem[];
}

/**
 * Return only the positioned items whose vertical band intersects the
 * scroll viewport (plus an overscan margin). This is the per-scroll-
 * frame hot path — it must stay O(log n + window), so `flatItems` must
 * be sorted by `y` ascending (`computeLineageTimeline` guarantees it).
 */
export function virtualizeLineageItems(
  flatItems: ReadonlyArray<PositionedLineageItem>,
  scrollTop: number,
  viewportHeight: number,
  overscan = 240,
): VirtualLineageWindow {
  const top = scrollTop - overscan;
  const bottom = scrollTop + viewportHeight + overscan;
  // Binary search for the first item whose bottom edge >= `top`.
  let lo = 0;
  let hi = flatItems.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    const it = flatItems[mid];
    if (it.y + it.height < top) lo = mid + 1;
    else hi = mid;
  }
  const start = lo;
  let end = start;
  while (end < flatItems.length && flatItems[end].y <= bottom) end++;
  return { start, end, items: flatItems.slice(start, end) };
}

/**
 * Move keyboard focus through the time-sorted flat item list. Returns
 * the id of the item to focus next, or null when there is nothing to
 * focus. `direction` 1 = down (older), -1 = up (newer).
 */
export function lineageFocusStep(
  flatItems: ReadonlyArray<PositionedLineageItem>,
  currentId: string | null,
  direction: 1 | -1,
): string | null {
  if (flatItems.length === 0) return null;
  const idx = flatItems.findIndex((it) => it.item.id === currentId);
  if (idx === -1) {
    return flatItems[direction === 1 ? 0 : flatItems.length - 1].item.id;
  }
  const next = Math.min(flatItems.length - 1, Math.max(0, idx + direction));
  return flatItems[next].item.id;
}

/**
 * True when the viewport has scrolled within `threshold` px of the
 * bottom (further back in time) and older events remain unpaged.
 */
export function shouldPaginateLineage(
  scrollTop: number,
  viewportHeight: number,
  totalHeight: number,
  loadedCount: number,
  availableCount: number,
  threshold = 320,
): boolean {
  if (loadedCount >= availableCount) return false;
  return scrollTop + viewportHeight >= totalHeight - threshold;
}

/** Public projection: the nodes a public reader is allowed to see. The
 *  strict rule — private events are dropped entirely, leaving no stub. */
export function publicLineageNodes(
  lineage: Lineage,
): LineageNode[] {
  return lineage.nodes.filter((n) => n.publicVisible);
}
