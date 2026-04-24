"use client";

import { useMemo, useState } from "react";
import type { PublicOpinion } from "@/lib/currentsTypes";
import { OpinionCard } from "./OpinionCard";

export function TopicClusters({ opinions }: { opinions: PublicOpinion[] }) {
  const groups = useMemo(() => {
    const by = new Map<string, PublicOpinion[]>();
    for (const op of opinions) {
      const key = op.topic_hint || "unclassified";
      const arr = by.get(key) ?? [];
      arr.push(op);
      by.set(key, arr);
    }
    return [...by.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [opinions]);

  return (
    <div data-testid="topic-clusters">
      {groups.map(([topic, ops]) => (
        <TopicGroup key={topic} topic={topic} ops={ops} />
      ))}
    </div>
  );
}

function TopicGroup({ topic, ops }: { topic: string; ops: PublicOpinion[] }) {
  const [open, setOpen] = useState(true);
  return (
    <section style={{ marginBottom: "1.4rem" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        data-testid="topic-group-toggle"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.45rem",
          background: "transparent",
          border: "none",
          color: "var(--currents-gold)",
          textTransform: "uppercase",
          letterSpacing: "0.12em",
          fontSize: "0.78rem",
          padding: "0.3rem 0",
          cursor: "pointer",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          marginBottom: "0.55rem",
        }}
      >
        <span aria-hidden>{open ? "▾" : "▸"}</span>
        <span>{topic}</span>
        <span
          style={{
            color: "var(--currents-parchment-dim)",
            letterSpacing: "0.08em",
          }}
        >
          ({ops.length})
        </span>
      </button>
      {open
        ? ops.map((op) => <OpinionCard key={op.id} op={op} />)
        : null}
    </section>
  );
}
