"use client";

import LineageEventCard from "./LineageEventCard";
import type { LineageLaneModel, PositionedLineageItem } from "@/lib/lineage";

/**
 * One swim-lane column. The lane body is a fixed-height relative box
 * (height = the timeline's total height) so the shared scrollbar
 * reflects the whole lineage; only the *virtualised* subset of cards
 * for this lane is actually mounted, each absolutely positioned at its
 * time-derived `y`.
 */

type Props = {
  lane: LineageLaneModel;
  /** virtualised items for this lane only (already y-windowed). */
  items: PositionedLineageItem[];
  totalHeight: number;
  focusedId: string | null;
  expandedGroups: ReadonlySet<string>;
  onToggleGroup: (id: string) => void;
  onFocusItem: (id: string) => void;
  publicMode?: boolean;
};

export default function LineageLane({
  lane,
  items,
  totalHeight,
  focusedId,
  expandedGroups,
  onToggleGroup,
  onFocusItem,
  publicMode,
}: Props) {
  return (
    <section
      aria-label={`${lane.label} lane`}
      data-lineage-lane={lane.id}
      style={{
        flex: "1 1 0",
        minWidth: 168,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 10,
          background: "var(--stone)",
          borderBottom: "1px solid var(--stroke)",
          padding: "0.35rem 0.5rem",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "0.4rem",
        }}
      >
        <span
          className="mono"
          style={{
            fontSize: "0.56rem",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
          }}
        >
          {lane.label}
        </span>
        <span
          className="mono"
          style={{ fontSize: "0.56rem", color: "var(--parchment-dim)" }}
        >
          {lane.eventCount}
        </span>
      </header>

      <div
        role="list"
        style={{
          position: "relative",
          height: totalHeight,
          padding: "0 0.4rem",
          borderRight: "1px solid var(--stroke)",
        }}
      >
        {lane.eventCount === 0 ? (
          <p
            className="mono"
            style={{
              position: "absolute",
              top: 8,
              left: 8,
              right: 8,
              fontSize: "0.55rem",
              color: "var(--parchment-dim)",
              opacity: 0.7,
            }}
          >
            —
          </p>
        ) : null}
        {items.map((pi) => (
          <div
            key={pi.item.id}
            style={{
              position: "absolute",
              top: pi.y,
              left: "0.4rem",
              right: "0.4rem",
            }}
          >
            <LineageEventCard
              item={pi.item}
              focused={focusedId === pi.item.id}
              expanded={
                pi.item.type === "group" && expandedGroups.has(pi.item.id)
              }
              onToggleExpand={() => onToggleGroup(pi.item.id)}
              onFocus={() => onFocusItem(pi.item.id)}
              publicMode={publicMode}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
