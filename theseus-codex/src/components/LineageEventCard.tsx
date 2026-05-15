"use client";

import Link from "next/link";

import {
  LINEAGE_KIND_COLORS,
  LINEAGE_KIND_LABELS,
  type LineageNode,
  type LineageTimelineItem,
} from "@/lib/lineage";

/**
 * One card in a lineage swim lane — either a single event or a
 * collapsed "group pill" standing in for a run of adjacent same-lane
 * events. The pill expands on click; the parent lane owns the
 * expanded-set state so keyboard `Enter` can toggle it too.
 *
 * Cards are absolutely positioned by `LineageLane`; this component only
 * renders content, never its own offset.
 */

type Props = {
  item: LineageTimelineItem;
  focused: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
  onFocus: () => void;
  /** Public view drops the private badge entirely (private events are
   *  never passed to the public timeline in the first place). */
  publicMode?: boolean;
};

function fmt(ms: number): string {
  return new Date(ms).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const cardShell = (focused: boolean): React.CSSProperties => ({
  border: focused ? "1px solid var(--gold)" : "1px solid var(--stroke)",
  borderLeftWidth: 3,
  borderRadius: 3,
  background: "var(--stone-light)",
  padding: "0.4rem 0.55rem",
  boxShadow: focused ? "var(--glow-md)" : "none",
  outline: "none",
  cursor: "default",
  transition: "border-color 120ms ease, box-shadow 120ms ease",
});

const kindTag = (kind: LineageNode["kind"]): React.CSSProperties => ({
  fontSize: "0.5rem",
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  color: "var(--amber-dim)",
  fontFamily:
    "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
  borderLeft: `3px solid ${LINEAGE_KIND_COLORS[kind] ?? "var(--amber)"}`,
  paddingLeft: "0.3rem",
});

function EventBody({
  node,
  publicMode,
}: {
  node: LineageNode;
  publicMode?: boolean;
}) {
  return (
    <div>
      <div
        style={{
          display: "flex",
          gap: "0.4rem",
          alignItems: "baseline",
          justifyContent: "space-between",
        }}
      >
        <span className="mono" style={kindTag(node.kind)}>
          {LINEAGE_KIND_LABELS[node.kind] ?? node.kind}
        </span>
        {!publicMode && !node.publicVisible ? (
          <span
            className="mono"
            title="Private — omitted from the public lineage."
            style={{
              fontSize: "0.48rem",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              color: "var(--ember)",
            }}
          >
            private
          </span>
        ) : null}
      </div>
      <div
        style={{
          fontSize: "0.82rem",
          color: "var(--parchment)",
          lineHeight: 1.3,
          marginTop: "0.15rem",
          overflow: "hidden",
          textOverflow: "ellipsis",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
        }}
      >
        {node.recordUrl ? (
          <Link
            href={node.recordUrl}
            style={{ color: "var(--amber)", textDecoration: "none" }}
          >
            {node.label}
          </Link>
        ) : (
          node.label
        )}
      </div>
      <div
        className="mono"
        style={{
          fontSize: "0.55rem",
          color: "var(--parchment-dim)",
          marginTop: "0.15rem",
        }}
      >
        {fmt(Date.parse(node.timestamp))}
      </div>
    </div>
  );
}

export default function LineageEventCard({
  item,
  focused,
  expanded,
  onToggleExpand,
  onFocus,
  publicMode,
}: Props) {
  if (item.type === "event") {
    return (
      <div
        data-lineage-event-id={item.id}
        data-lineage-focused={focused ? "true" : undefined}
        role="listitem"
        tabIndex={-1}
        onMouseDown={onFocus}
        style={{
          ...cardShell(focused),
          borderLeftColor:
            LINEAGE_KIND_COLORS[item.node.kind] ?? "var(--amber)",
        }}
      >
        <EventBody node={item.node} publicMode={publicMode} />
      </div>
    );
  }

  // Group pill.
  const kinds = Array.from(new Set(item.nodes.map((n) => n.kind)));
  const kindSummary = kinds
    .map((k) => LINEAGE_KIND_LABELS[k] ?? k)
    .join(" · ");
  return (
    <div
      data-lineage-group-id={item.id}
      data-lineage-focused={focused ? "true" : undefined}
      role="listitem"
      style={{
        ...cardShell(focused),
        borderLeftColor: "var(--amber-dim)",
        zIndex: expanded ? 20 : undefined,
        position: expanded ? "relative" : undefined,
      }}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={onToggleExpand}
        onMouseDown={onFocus}
        style={{
          all: "unset",
          cursor: "pointer",
          display: "block",
          width: "100%",
        }}
      >
        <div
          style={{
            display: "flex",
            gap: "0.4rem",
            alignItems: "baseline",
            justifyContent: "space-between",
          }}
        >
          <span
            className="mono"
            style={{
              fontSize: "0.5rem",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
            }}
          >
            {item.nodes.length} grouped events
          </span>
          <span
            aria-hidden
            style={{ fontSize: "0.65rem", color: "var(--parchment-dim)" }}
          >
            {expanded ? "▾" : "▸"}
          </span>
        </div>
        <div
          style={{
            fontSize: "0.8rem",
            color: "var(--parchment)",
            lineHeight: 1.3,
          }}
        >
          {kindSummary}
        </div>
        <div
          className="mono"
          style={{
            fontSize: "0.55rem",
            color: "var(--parchment-dim)",
            marginTop: "0.15rem",
          }}
        >
          {fmt(item.startMs)} — {fmt(item.endMs)}
        </div>
      </button>

      {expanded ? (
        <div
          style={{
            marginTop: "0.4rem",
            paddingTop: "0.4rem",
            borderTop: "1px solid var(--stroke)",
            display: "flex",
            flexDirection: "column",
            gap: "0.35rem",
            background: "var(--stone-light)",
          }}
        >
          {item.nodes.map((n) => (
            <div
              key={n.id}
              data-lineage-event-id={n.id}
              style={{
                borderLeft: `2px solid ${
                  LINEAGE_KIND_COLORS[n.kind] ?? "var(--amber)"
                }`,
                paddingLeft: "0.4rem",
              }}
            >
              <EventBody node={n} publicMode={publicMode} />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
