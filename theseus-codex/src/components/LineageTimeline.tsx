"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import LineageEventCard from "./LineageEventCard";
import LineageLane from "./LineageLane";
import LineageMobileSheet from "./LineageMobileSheet";
import {
  LINEAGE_LANES,
  LINEAGE_PAGE_SIZE,
  LINEAGE_VIEWPORT_HEIGHT,
  computeLineageTimeline,
  defaultLaneVisibility,
  lineageFocusStep,
  lineageTimeExtent,
  shouldPaginateLineage,
  virtualizeLineageItems,
  type Lineage,
  type LineageLaneId,
  type PositionedLineageItem,
} from "@/lib/lineage";

const LANE_LABEL: Record<LineageLaneId, string> = Object.fromEntries(
  LINEAGE_LANES.map((l) => [l.id, l.label]),
) as Record<LineageLaneId, string>;

/**
 * Layered, virtualised lineage timeline (Round 17 prompt 17 v2).
 *
 * Reorganises the flat v1 lineage into horizontal swim lanes — one
 * column per phase — with vertical position encoding time. A toolbar
 * filters lanes and the time range; adjacent same-lane events collapse
 * into expandable group pills; the scroll body is virtualised so a
 * 1,000-event lineage stays responsive (initial paint = the 100 most
 * recent events, scrolling back in time pages older ones in).
 *
 * Keyboard: the scroll body is a focusable region (the keyboard
 * convention from Round 17 prompt 36 — j/k or arrows navigate, editable
 * inputs are never hijacked). j/k are scoped to this region rather than
 * registered window-wide so they don't collide with the conclusion
 * page's own j/k tab keymap.
 *
 * No charting framework: plain absolutely-positioned divs, the same
 * primitive the explorer canvas and cascade tree are built from.
 */

type Props = {
  lineage: Lineage;
  /** Public view: private events are dropped entirely, not redacted. */
  publicMode?: boolean;
};

function fmtDate(ms: number): string {
  return new Date(ms).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * Viewport switch for the lineage view. Both the desktop swim-lane body
 * and the mobile single-column body ship in the HTML; CSS picks one by
 * width, so there is no JS viewport sniffing and no post-hydration
 * layout shift. The root reserves bottom room for the fixed
 * LineageMobileSheet so the footer and last card stay reachable above
 * the iOS Safari bottom bar.
 */
const lineageResponsiveCss = `
.lineage-mobile-only { display: none; }
@media (max-width: 720px) {
  .lineage-desktop-only { display: none; }
  .lineage-mobile-only { display: block; }
  .lineage-timeline-root {
    padding-bottom: calc(4.25rem + env(safe-area-inset-bottom, 0px));
  }
}
.lineage-mobile-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}
.lineage-mobile-item { display: block; }
.lineage-mobile-lane-badge {
  display: inline-block;
  font-size: 0.5rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--amber-dim);
  margin-bottom: 0.2rem;
}
`;

export default function LineageTimeline({ lineage, publicMode }: Props) {
  // Strict public projection: private events never enter the model, so
  // there is nothing to leak — no "[redacted]" stub, no count, nothing.
  const nodes = useMemo(
    () =>
      publicMode
        ? lineage.nodes.filter((n) => n.publicVisible)
        : lineage.nodes,
    [lineage.nodes, publicMode],
  );

  const fullExtent = useMemo(() => lineageTimeExtent(nodes), [nodes]);
  const hasRange = fullExtent.max > fullExtent.min;

  const [visibleLanes, setVisibleLanes] = useState<
    Record<LineageLaneId, boolean>
  >(() => defaultLaneVisibility(nodes.length));
  const [timeRange, setTimeRange] = useState<[number, number]>(() => [
    fullExtent.min,
    fullExtent.max,
  ]);
  const [visibleCount, setVisibleCount] = useState(LINEAGE_PAGE_SIZE);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(
    LINEAGE_VIEWPORT_HEIGHT,
  );
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<ReadonlySet<string>>(
    () => new Set(),
  );

  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Re-seed the time range if the underlying lineage changes.
  useEffect(() => {
    setTimeRange([fullExtent.min, fullExtent.max]);
    setVisibleCount(LINEAGE_PAGE_SIZE);
  }, [fullExtent.min, fullExtent.max]);

  const model = useMemo(
    () =>
      computeLineageTimeline(nodes, {
        visibleLanes,
        timeRange: hasRange ? timeRange : null,
        visibleCount,
      }),
    [nodes, visibleLanes, timeRange, hasRange, visibleCount],
  );

  // Keep a clear focused element; reset if the focused item filtered out.
  useEffect(() => {
    if (model.flatItems.length === 0) {
      if (focusedId !== null) setFocusedId(null);
      return;
    }
    const stillThere = model.flatItems.some(
      (it) => it.item.id === focusedId,
    );
    if (!stillThere) setFocusedId(model.flatItems[0].item.id);
  }, [model, focusedId]);

  // Measure the scroll viewport so virtualisation tracks the real box.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof window === "undefined") return;
    const measure = () =>
      setViewportHeight(el.clientHeight || LINEAGE_VIEWPORT_HEIGHT);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  const virtual = useMemo(
    () =>
      virtualizeLineageItems(model.flatItems, scrollTop, viewportHeight),
    [model.flatItems, scrollTop, viewportHeight],
  );

  // Split the virtual window back out per lane for rendering.
  const itemsByLane = useMemo(() => {
    const map = new Map<LineageLaneId, PositionedLineageItem[]>();
    for (const lane of LINEAGE_LANES) map.set(lane.id, []);
    for (const pi of virtual.items) map.get(pi.lane)!.push(pi);
    return map;
  }, [virtual.items]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const st = el.scrollTop;
    setScrollTop(st);
    if (
      shouldPaginateLineage(
        st,
        el.clientHeight,
        model.totalHeight,
        visibleCount,
        model.availableEvents,
      )
    ) {
      setVisibleCount((c) =>
        Math.min(model.availableEvents, c + LINEAGE_PAGE_SIZE),
      );
    }
  }, [model.totalHeight, model.availableEvents, visibleCount]);

  const toggleGroup = useCallback((id: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const focusAndReveal = useCallback(
    (id: string | null) => {
      setFocusedId(id);
      if (!id) return;
      const el = scrollRef.current;
      const pos = model.flatItems.find((it) => it.item.id === id);
      if (!el || !pos) return;
      const top = pos.y;
      const bottom = pos.y + pos.height;
      if (top < el.scrollTop) el.scrollTop = Math.max(0, top - 16);
      else if (bottom > el.scrollTop + el.clientHeight) {
        el.scrollTop = bottom - el.clientHeight + 16;
      }
    },
    [model.flatItems],
  );

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const key = e.key.toLowerCase();
      if (key === "j" || key === "arrowdown") {
        e.preventDefault();
        focusAndReveal(lineageFocusStep(model.flatItems, focusedId, 1));
      } else if (key === "k" || key === "arrowup") {
        e.preventDefault();
        focusAndReveal(lineageFocusStep(model.flatItems, focusedId, -1));
      } else if (key === "enter" || key === " ") {
        const focused = model.flatItems.find(
          (it) => it.item.id === focusedId,
        );
        if (focused?.item.type === "group") {
          e.preventDefault();
          toggleGroup(focused.item.id);
        }
      }
    },
    [model.flatItems, focusedId, focusAndReveal, toggleGroup],
  );

  const setLane = (id: LineageLaneId, on: boolean) =>
    setVisibleLanes((prev) => ({ ...prev, [id]: on }));

  const visibleLaneModels = model.lanes.filter((l) => l.visible);

  // ── Render ────────────────────────────────────────────────────────

  if (nodes.length === 0) {
    return (
      <p className="mono" style={{ color: "var(--parchment-dim)" }}>
        {publicMode
          ? "No public lineage steps have been recorded for this conclusion."
          : "No lineage events recorded yet."}
      </p>
    );
  }

  return (
    <div className="lineage-timeline-root">
      <style>{lineageResponsiveCss}</style>
      {/* Toolbar — lane checkboxes + time-range slider. Desktop only:
          on a phone the lane checkboxes move to LineageMobileSheet (a
          sticky bottom sheet) and the timeline reflows to one column. */}
      <div
        className="lineage-desktop-only"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem 1.1rem",
          alignItems: "center",
          padding: "0.6rem 0.75rem",
          border: "1px solid var(--stroke)",
          borderRadius: 3,
          background: "var(--stone)",
          marginBottom: "0.85rem",
        }}
      >
        <fieldset
          style={{
            border: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexWrap: "wrap",
            gap: "0.55rem",
            alignItems: "center",
          }}
        >
          <legend
            className="mono"
            style={{
              fontSize: "0.55rem",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              float: "left",
              marginRight: "0.5rem",
            }}
          >
            Lanes
          </legend>
          {model.lanes.map((lane) => (
            <label
              key={lane.id}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.3rem",
                fontSize: "0.7rem",
                color: lane.visible
                  ? "var(--parchment)"
                  : "var(--parchment-dim)",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={lane.visible}
                onChange={(e) => setLane(lane.id, e.target.checked)}
                aria-label={`Show ${lane.label} lane`}
              />
              {lane.label}
              <span
                className="mono"
                style={{ color: "var(--parchment-dim)", fontSize: "0.6rem" }}
              >
                {lane.eventCount}
              </span>
            </label>
          ))}
        </fieldset>

        {hasRange ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              flex: "1 1 240px",
              minWidth: 200,
            }}
          >
            <span
              className="mono"
              style={{
                fontSize: "0.55rem",
                letterSpacing: "0.2em",
                textTransform: "uppercase",
                color: "var(--amber-dim)",
              }}
            >
              Time
            </span>
            <input
              type="range"
              min={fullExtent.min}
              max={fullExtent.max}
              value={timeRange[0]}
              step={Math.max(
                1,
                Math.round((fullExtent.max - fullExtent.min) / 1000),
              )}
              onChange={(e) => {
                const v = Number(e.target.value);
                setTimeRange(([, hi]) => [Math.min(v, hi), hi]);
              }}
              aria-label="Earliest event shown"
              style={{ flex: 1 }}
            />
            <input
              type="range"
              min={fullExtent.min}
              max={fullExtent.max}
              value={timeRange[1]}
              step={Math.max(
                1,
                Math.round((fullExtent.max - fullExtent.min) / 1000),
              )}
              onChange={(e) => {
                const v = Number(e.target.value);
                setTimeRange(([lo]) => [lo, Math.max(v, lo)]);
              }}
              aria-label="Latest event shown"
              style={{ flex: 1 }}
            />
            <span
              className="mono"
              style={{
                fontSize: "0.55rem",
                color: "var(--parchment-dim)",
                whiteSpace: "nowrap",
              }}
            >
              {fmtDate(timeRange[0])} – {fmtDate(timeRange[1])}
            </span>
            {(timeRange[0] !== fullExtent.min ||
              timeRange[1] !== fullExtent.max) && (
              <button
                type="button"
                onClick={() =>
                  setTimeRange([fullExtent.min, fullExtent.max])
                }
                className="mono"
                style={{
                  background: "transparent",
                  border: "1px solid var(--stroke)",
                  borderRadius: 2,
                  color: "var(--parchment-dim)",
                  fontSize: "0.55rem",
                  padding: "0.15rem 0.4rem",
                  cursor: "pointer",
                }}
              >
                reset
              </button>
            )}
          </div>
        ) : null}
      </div>

      {/* Scroll body — focusable region, virtualised, lanes side by side.
          Desktop only; the mobile single-column body follows. */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        onKeyDown={onKeyDown}
        tabIndex={0}
        role="application"
        aria-label="Lineage timeline — press j and k or the arrow keys to navigate events"
        className="lineage-desktop-only"
        style={{
          position: "relative",
          height: LINEAGE_VIEWPORT_HEIGHT,
          overflowY: "auto",
          overflowX: "auto",
          border: "1px solid var(--stroke)",
          borderRadius: 3,
          outline: "none",
        }}
      >
        {visibleLaneModels.length === 0 ? (
          <p
            className="mono"
            style={{
              padding: "1rem",
              color: "var(--parchment-dim)",
              fontSize: "0.7rem",
            }}
          >
            All lanes hidden — enable a lane above to see events.
          </p>
        ) : (
          <div style={{ display: "flex", minHeight: model.totalHeight }}>
            {visibleLaneModels.map((lane) => (
              <LineageLane
                key={lane.id}
                lane={lane}
                items={itemsByLane.get(lane.id) ?? []}
                totalHeight={model.totalHeight}
                focusedId={focusedId}
                expandedGroups={expandedGroups}
                onToggleGroup={toggleGroup}
                onFocusItem={focusAndReveal}
                publicMode={publicMode}
              />
            ))}
          </div>
        )}
      </div>

      {/* Mobile single-column body. The swim-lane layout needs horizontal
          room the phone does not have, so below 720px the lanes collapse
          into one chronological stack — every event keeps a lane badge so
          the phase is still legible. `model.flatItems` is already the
          time-sorted projection across visible lanes. The bottom padding
          clears the fixed LineageMobileSheet. */}
      <div
        className="lineage-mobile-only lineage-mobile-column"
        data-testid="lineage-mobile-column"
      >
        {model.flatItems.length === 0 ? (
          <p
            className="mono"
            style={{
              padding: "1rem",
              color: "var(--parchment-dim)",
              fontSize: "0.72rem",
              border: "1px solid var(--stroke)",
              borderRadius: 3,
            }}
          >
            {visibleLaneModels.length === 0
              ? "All lanes hidden — open the Lanes sheet below to show events."
              : "No events in the current view."}
          </p>
        ) : (
          <div className="lineage-mobile-list" role="list">
            {model.flatItems.map((pi) => (
              <div key={pi.item.id} className="lineage-mobile-item">
                <span className="mono lineage-mobile-lane-badge">
                  {LANE_LABEL[pi.lane]}
                </span>
                <LineageEventCard
                  item={pi.item}
                  focused={focusedId === pi.item.id}
                  expanded={
                    pi.item.type === "group" &&
                    expandedGroups.has(pi.item.id)
                  }
                  onToggleExpand={() => toggleGroup(pi.item.id)}
                  onFocus={() => setFocusedId(pi.item.id)}
                  publicMode={publicMode}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <LineageMobileSheet lanes={model.lanes} onToggleLane={setLane} />

      {/* Footer — counts + pagination state */}
      <p
        className="mono"
        style={{
          marginTop: "0.75rem",
          fontSize: "0.58rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--parchment-dim)",
        }}
      >
        {model.shownEvents} shown · {model.totalEvents} in view ·{" "}
        {model.availableEvents} total
        {visibleCount < model.availableEvents
          ? " · scroll back in time to load older events"
          : ""}
      </p>
    </div>
  );
}
