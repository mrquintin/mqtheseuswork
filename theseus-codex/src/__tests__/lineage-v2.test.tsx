import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

/**
 * Conclusion-lineage visualization v2 (Round 17 prompt 17 v2).
 *
 * The v2 refinement is judged on three things, all asserted here:
 *   - virtualization keeps a 1,000-event lineage inside the 16ms frame
 *     budget (p95) by rendering only the scrolled-into-view window;
 *   - lane filtering removes a lane's events from the timeline model
 *     (and so from the DOM) when its checkbox is off;
 *   - the public visibility filter omits private events entirely — not
 *     as "[redacted]" stubs — so a public reader cannot tell a private
 *     step ever existed.
 *
 * Plus coverage of the supporting pieces: event grouping, the
 * collapse-source-ingestion-on-long-lineages default, and keyboard
 * navigation through the flat item list.
 *
 * The test environment is node (no jsdom): components are exercised via
 * `renderToStaticMarkup`, and the heavy lifting is verified through the
 * pure projection helpers in `@/lib/lineage`.
 */

// `@/lib/lineage` imports the Prisma client for its server-side
// assembler; the v2 rendering helpers under test never touch the DB, so
// a bare stub keeps the module graph importable in the node test env.
vi.mock("@/lib/db", () => ({ db: {} }));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import LineageTimeline from "@/components/LineageTimeline";
import {
  LINEAGE_LANES,
  computeLineageTimeline,
  defaultLaneVisibility,
  groupLaneEvents,
  laneForKind,
  lineageFocusStep,
  publicLineageNodes,
  virtualizeLineageItems,
  type Lineage,
  type LineageNode,
  type LineageNodeKind,
} from "@/lib/lineage";

// ── Fixtures ────────────────────────────────────────────────────────-

const ALL_KINDS: LineageNodeKind[] = [
  "source",
  "claim",
  "methodology",
  "method_invocation",
  "peer_review",
  "drift",
  "revision",
  "calibration",
  "conclusion",
  "publication",
  "citation",
];

const BASE_MS = Date.parse("2026-01-01T00:00:00.000Z");
const HOUR = 60 * 60 * 1000;

function node(over: Partial<LineageNode> & { id: string }): LineageNode {
  return {
    id: over.id,
    kind: over.kind ?? "claim",
    label: over.label ?? over.id,
    timestamp: over.timestamp ?? new Date(BASE_MS).toISOString(),
    summary: over.summary ?? "",
    payload: over.payload ?? {},
    publicVisible: over.publicVisible ?? true,
    recordUrl: over.recordUrl ?? "",
  };
}

/**
 * A synthetic lineage of `count` events spaced 3h apart, cycling through
 * every node kind so all seven lanes populate. 3h spacing keeps any one
 * lane's events well outside the 1h grouping window, so `count` distinct
 * timeline items survive into the model — the worst case for the
 * virtualizer.
 */
function syntheticLineage(count: number): Lineage {
  const nodes: LineageNode[] = [];
  for (let i = 0; i < count; i++) {
    const kind = ALL_KINDS[i % ALL_KINDS.length];
    nodes.push(
      node({
        id: `${kind}:${i}`,
        kind,
        label: `event ${i} (${kind})`,
        timestamp: new Date(BASE_MS + i * 3 * HOUR).toISOString(),
        publicVisible: i % 2 === 0,
      }),
    );
  }
  return {
    conclusionId: "conc-synthetic",
    assembledAt: new Date(BASE_MS + count * 3 * HOUR).toISOString(),
    nodes,
    edges: [],
  };
}

// ── A. Lane assignment ──────────────────────────────────────────────-

describe("lane assignment", () => {
  it("maps every node kind into one of the seven phase lanes", () => {
    const laneIds = new Set(LINEAGE_LANES.map((l) => l.id));
    expect(laneIds.size).toBe(7);
    for (const kind of ALL_KINDS) {
      expect(laneIds.has(laneForKind(kind))).toBe(true);
    }
    expect(laneForKind("source")).toBe("source-ingestion");
    expect(laneForKind("claim")).toBe("extraction");
    expect(laneForKind("method_invocation")).toBe("methodology");
    expect(laneForKind("peer_review")).toBe("review");
    expect(laneForKind("revision")).toBe("revision");
    expect(laneForKind("conclusion")).toBe("publication");
    expect(laneForKind("citation")).toBe("outcomes");
  });

  it("collapses source-ingestion by default only on long lineages", () => {
    const short = defaultLaneVisibility(5);
    const long = defaultLaneVisibility(500);

    // Methodology / review / revision / outcomes are always on.
    for (const id of [
      "methodology",
      "review",
      "revision",
      "outcomes",
    ] as const) {
      expect(short[id]).toBe(true);
      expect(long[id]).toBe(true);
    }

    // Source-ingestion is on for a short chain, collapsed for a long one.
    expect(short["source-ingestion"]).toBe(true);
    expect(long["source-ingestion"]).toBe(false);
  });
});

// ── B. Lane filtering ───────────────────────────────────────────────-

describe("lane filtering", () => {
  const lineage = syntheticLineage(60);
  const everyLaneOn = Object.fromEntries(
    LINEAGE_LANES.map((l) => [l.id, true]),
  );

  it("includes a lane's events when its checkbox is on", () => {
    const model = computeLineageTimeline(lineage.nodes, {
      visibleLanes: everyLaneOn,
      visibleCount: 1000,
    });
    const reviewKinds = model.flatItems.flatMap((pi) =>
      pi.item.type === "event"
        ? [pi.item.node.kind]
        : pi.item.nodes.map((n) => n.kind),
    );
    expect(reviewKinds).toContain("peer_review");
    expect(reviewKinds).toContain("drift");
  });

  it("drops a lane's events from the flat model when its checkbox is off", () => {
    const model = computeLineageTimeline(lineage.nodes, {
      visibleLanes: { ...everyLaneOn, review: false },
      visibleCount: 1000,
    });

    // No review-lane item survives into the rendered (flat) list...
    for (const pi of model.flatItems) {
      expect(pi.lane).not.toBe("review");
      const kinds =
        pi.item.type === "event"
          ? [pi.item.node.kind]
          : pi.item.nodes.map((n) => n.kind);
      expect(kinds).not.toContain("peer_review");
      expect(kinds).not.toContain("drift");
    }

    // ...but the lane is still reported (with its count) for the toolbar.
    const reviewLane = model.lanes.find((l) => l.id === "review");
    expect(reviewLane).toBeDefined();
    expect(reviewLane!.visible).toBe(false);
    expect(reviewLane!.eventCount).toBeGreaterThan(0);
  });

  it("omits a hidden lane's events from the rendered DOM", () => {
    // source-ingestion is collapsed by default on this long (60-event)
    // lineage, so its events must not appear in the static markup.
    const html = renderToStaticMarkup(<LineageTimeline lineage={lineage} />);
    expect(html).toContain('data-lineage-lane="review"');
    expect(html).not.toContain('data-lineage-lane="source-ingestion"');
  });
});

// ── C. Event grouping ───────────────────────────────────────────────-

describe("event grouping", () => {
  it("collapses adjacent same-lane events within one hour into a pill", () => {
    // Five peer-review verdicts, 10 minutes apart — all within an hour.
    const verdicts = Array.from({ length: 5 }, (_, i) =>
      node({
        id: `review:${i}`,
        kind: "peer_review",
        timestamp: new Date(BASE_MS + i * 10 * 60 * 1000).toISOString(),
      }),
    );
    const items = groupLaneEvents(verdicts, "review");
    expect(items).toHaveLength(1);
    expect(items[0].type).toBe("group");
    if (items[0].type === "group") {
      expect(items[0].nodes).toHaveLength(5);
    }
  });

  it("leaves events spread beyond the window as individual cards", () => {
    const spread = [
      node({ id: "a", kind: "peer_review", timestamp: new Date(BASE_MS).toISOString() }),
      node({
        id: "b",
        kind: "peer_review",
        timestamp: new Date(BASE_MS + 5 * HOUR).toISOString(),
      }),
    ];
    const items = groupLaneEvents(spread, "review");
    expect(items).toHaveLength(2);
    expect(items.every((it) => it.type === "event")).toBe(true);
  });

  it("surfaces a group item in the computed timeline model", () => {
    const verdicts = Array.from({ length: 4 }, (_, i) =>
      node({
        id: `review:${i}`,
        kind: "peer_review",
        timestamp: new Date(BASE_MS + i * 12 * 60 * 1000).toISOString(),
      }),
    );
    const model = computeLineageTimeline(verdicts, {
      visibleLanes: { review: true },
      visibleCount: 100,
    });
    expect(model.flatItems).toHaveLength(1);
    expect(model.flatItems[0].item.type).toBe("group");
  });
});

// ── D. Virtualization & frame budget ────────────────────────────────-

describe("virtualization keeps a 1,000-event lineage responsive", () => {
  const lineage = syntheticLineage(1000);
  const visibleLanes = defaultLaneVisibility(lineage.nodes.length);

  it("initial paint loads only the most-recent page of events", () => {
    const model = computeLineageTimeline(lineage.nodes, { visibleLanes });
    // Default page size is 100: the model holds ~100 events, not 1,000.
    expect(model.availableEvents).toBe(1000);
    expect(model.totalEvents).toBeLessThanOrEqual(100);
    // The newest event in the lineage is in the loaded page.
    const newest = lineage.nodes[lineage.nodes.length - 1];
    const loadedIds = new Set(
      model.lanes.flatMap((l) =>
        l.items.flatMap((pi) =>
          pi.item.type === "event"
            ? [pi.item.node.id]
            : pi.item.nodes.map((n) => n.id),
        ),
      ),
    );
    expect(loadedIds.has(newest.id)).toBe(true);
  });

  it("flat items are y-sorted so the virtualizer can binary-search", () => {
    const model = computeLineageTimeline(lineage.nodes, {
      visibleLanes,
      visibleCount: 1000,
    });
    for (let i = 1; i < model.flatItems.length; i++) {
      expect(model.flatItems[i].y).toBeGreaterThanOrEqual(
        model.flatItems[i - 1].y,
      );
    }
  });

  it("renders only a bounded window and stays under the 16ms p95 budget", () => {
    // Worst case: the whole 1,000-event lineage paged in at once.
    const model = computeLineageTimeline(lineage.nodes, {
      visibleLanes,
      visibleCount: 1000,
    });
    expect(model.flatItems.length).toBeGreaterThan(500);

    const viewportHeight = 560;
    const frames = 600;
    const maxScroll = Math.max(1, model.totalHeight - viewportHeight);
    const timings: number[] = [];
    let maxWindow = 0;
    let checksum = 0;

    for (let f = 0; f < frames; f++) {
      // Sweep the viewport across the full timeline, back and forth.
      const phase = f / frames;
      const scrollTop =
        (phase < 0.5 ? phase * 2 : 2 - phase * 2) * maxScroll;
      const t0 = performance.now();
      const win = virtualizeLineageItems(
        model.flatItems,
        scrollTop,
        viewportHeight,
      );
      const t1 = performance.now();
      timings.push(t1 - t0);
      maxWindow = Math.max(maxWindow, win.items.length);
      checksum += win.items.length;
    }

    expect(checksum).toBeGreaterThan(0);

    // Virtualization actually bounds the work: each frame mounts a
    // small slice, never the whole 1,000-event lineage.
    expect(maxWindow).toBeLessThan(model.flatItems.length / 3);

    timings.sort((a, b) => a - b);
    const p95 = timings[Math.floor(timings.length * 0.95)];
    expect(p95).toBeLessThan(16);
  });

  it("paginates older events as the viewport scrolls back in time", () => {
    const page1 = computeLineageTimeline(lineage.nodes, {
      visibleLanes,
      visibleCount: 100,
    });
    const page2 = computeLineageTimeline(lineage.nodes, {
      visibleLanes,
      visibleCount: 200,
    });
    expect(page2.totalEvents).toBeGreaterThan(page1.totalEvents);
    expect(page2.totalHeight).toBeGreaterThanOrEqual(page1.totalHeight);
  });

  it("static markup mounts only the virtualized window, not all 1,000 events", () => {
    const html = renderToStaticMarkup(<LineageTimeline lineage={lineage} />);
    const mounted = (html.match(/data-lineage-event-id=/g) ?? []).length;
    expect(mounted).toBeGreaterThan(0);
    expect(mounted).toBeLessThan(200);
  });
});

// ── E. Keyboard navigation ──────────────────────────────────────────-

describe("keyboard navigation through the timeline", () => {
  const model = computeLineageTimeline(syntheticLineage(40).nodes, {
    visibleLanes: Object.fromEntries(
      LINEAGE_LANES.map((l) => [l.id, true]),
    ),
    visibleCount: 1000,
  });

  it("steps focus forward and backward through the flat item list", () => {
    const first = lineageFocusStep(model.flatItems, null, 1);
    expect(first).toBe(model.flatItems[0].item.id);

    const second = lineageFocusStep(model.flatItems, first, 1);
    expect(second).toBe(model.flatItems[1].item.id);

    const back = lineageFocusStep(model.flatItems, second, -1);
    expect(back).toBe(first);
  });

  it("clamps at the ends instead of wrapping", () => {
    const firstId = model.flatItems[0].item.id;
    const lastId = model.flatItems[model.flatItems.length - 1].item.id;
    expect(lineageFocusStep(model.flatItems, firstId, -1)).toBe(firstId);
    expect(lineageFocusStep(model.flatItems, lastId, 1)).toBe(lastId);
  });

  it("exposes the scroll body as a focusable, labelled region", () => {
    const html = renderToStaticMarkup(
      <LineageTimeline lineage={syntheticLineage(12)} />,
    );
    expect(html).toContain('tabindex="0"');
    expect(html).toMatch(/aria-label="Lineage timeline[^"]*j and k/);
  });
});

// ── F. Public visibility filter ─────────────────────────────────────-

describe("public lineage omits private events without leaking them", () => {
  // A lineage with private events sitting in default-visible lanes
  // (review, revision) and inside the initial window — so if the filter
  // failed, they would render.
  const mixed: Lineage = {
    conclusionId: "conc-public-test",
    assembledAt: new Date(BASE_MS + 10 * HOUR).toISOString(),
    nodes: [
      node({
        id: "source:public-1",
        kind: "source",
        label: "Public source document",
        timestamp: new Date(BASE_MS).toISOString(),
        publicVisible: true,
      }),
      node({
        id: "drift:secret-1",
        kind: "drift",
        label: "ZZZ-PRIVATE-DRIFT-LEAK",
        summary: "internal-only-secret-rationale",
        timestamp: new Date(BASE_MS + 2 * HOUR).toISOString(),
        publicVisible: false,
      }),
      node({
        id: "revision:secret-2",
        kind: "revision",
        label: "ZZZ-PRIVATE-REVISION-LEAK",
        summary: "confidential-revision-note",
        timestamp: new Date(BASE_MS + 3 * HOUR).toISOString(),
        publicVisible: false,
      }),
      node({
        id: "conclusion:public-2",
        kind: "conclusion",
        label: "Public conclusion statement",
        timestamp: new Date(BASE_MS + 4 * HOUR).toISOString(),
        publicVisible: true,
      }),
      node({
        id: "publication:public-3",
        kind: "publication",
        label: "Published v1",
        timestamp: new Date(BASE_MS + 5 * HOUR).toISOString(),
        publicVisible: true,
      }),
    ],
    edges: [],
  };

  it("publicLineageNodes drops exactly the private nodes", () => {
    const pub = publicLineageNodes(mixed);
    expect(pub).toHaveLength(3);
    expect(pub.every((n) => n.publicVisible)).toBe(true);
    expect(pub.some((n) => n.id === "drift:secret-1")).toBe(false);
  });

  it("publicMode renders no private label, summary, id, or redaction stub", () => {
    const html = renderToStaticMarkup(
      <LineageTimeline lineage={mixed} publicMode />,
    );

    // Private content is entirely absent — not redacted, just gone.
    expect(html).not.toContain("ZZZ-PRIVATE-DRIFT-LEAK");
    expect(html).not.toContain("ZZZ-PRIVATE-REVISION-LEAK");
    expect(html).not.toContain("internal-only-secret-rationale");
    expect(html).not.toContain("confidential-revision-note");
    expect(html).not.toContain("drift:secret-1");
    expect(html).not.toContain("revision:secret-2");

    // No stub of any kind hints that a private step existed.
    expect(html.toLowerCase()).not.toContain("redacted");
    expect(html.toLowerCase()).not.toContain("private");

    // Public events still render, so we know the filter is not over-broad.
    expect(html).toContain("Public conclusion statement");
    expect(html).toContain("Public source document");
  });

  it("founder mode still shows private events — publicMode is what strips them", () => {
    const html = renderToStaticMarkup(<LineageTimeline lineage={mixed} />);
    expect(html).toContain("ZZZ-PRIVATE-DRIFT-LEAK");
    expect(html).toContain("ZZZ-PRIVATE-REVISION-LEAK");
  });

  it("the public footer counts only public events", () => {
    const model = computeLineageTimeline(publicLineageNodes(mixed), {
      visibleLanes: Object.fromEntries(
        LINEAGE_LANES.map((l) => [l.id, true]),
      ),
      visibleCount: 100,
    });
    // Three public events; the two private ones are not counted anywhere.
    expect(model.totalEvents).toBe(3);
    expect(model.availableEvents).toBe(3);
  });
});
