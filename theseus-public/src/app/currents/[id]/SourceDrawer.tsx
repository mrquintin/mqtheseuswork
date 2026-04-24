"use client";

import { useEffect, useRef, useState } from "react";
import type { PublicCitation, PublicSource } from "@/lib/currentsTypes";
import { SourceCard } from "./SourceCard";

// Flash duration for the active border when a deep-link lands on a source.
const FLASH_MS = 1400;

export function SourceDrawer({
  citations,
  sources,
}: {
  citations: PublicCitation[];
  sources: PublicSource[];
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const refs = useRef(new Map<string, HTMLDivElement>());

  useEffect(() => {
    const scrollToHash = () => {
      if (typeof window === "undefined") return;
      const h = window.location.hash;
      if (!h.startsWith("#src-")) return;
      const id = decodeURIComponent(h.slice(5));
      const el = refs.current.get(id);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setActiveId(id);
      const t = window.setTimeout(() => setActiveId(null), FLASH_MS);
      return () => window.clearTimeout(t);
    };
    scrollToHash();
    window.addEventListener("hashchange", scrollToHash);
    return () => window.removeEventListener("hashchange", scrollToHash);
  }, []);

  const sourcesById = new Map(sources.map((s) => [s.source_id, s]));

  return (
    <aside
      aria-label="Sources"
      data-testid="source-drawer"
      style={{
        background: "var(--currents-bg-elevated)",
        border: "1px solid var(--currents-border)",
        borderRadius: 3,
        padding: "1rem",
        maxHeight: "calc(100vh - 4rem)",
        overflowY: "auto",
        position: "sticky",
        top: "1rem",
      }}
    >
      <h3
        style={{
          margin: "0 0 0.7rem",
          fontSize: "0.78rem",
          color: "var(--currents-parchment-dim)",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          fontWeight: 600,
        }}
      >
        Sources cited ({citations.length})
      </h3>
      {citations.length === 0 ? (
        <p
          style={{
            fontSize: "0.82rem",
            fontStyle: "italic",
            color: "var(--currents-parchment-dim)",
            margin: 0,
          }}
        >
          The firm did not cite any sources for this opinion.
        </p>
      ) : null}
      {citations.map((c, i) => {
        const src = sourcesById.get(c.source_id);
        if (!src) {
          return (
            <div
              key={`${c.source_id}-${i}`}
              data-testid="missing-source"
              style={{
                padding: "0.6rem",
                border: "1px dashed var(--currents-border)",
                color: "var(--currents-amber, #c79a3a)",
                fontSize: "0.78rem",
                marginBottom: "0.5rem",
                fontStyle: "italic",
                borderRadius: 3,
              }}
            >
              Missing source (id {c.source_id}). It may have been revoked
              since this opinion was generated.
            </div>
          );
        }
        return (
          <SourceCard
            key={`${c.source_id}-${i}`}
            citation={c}
            source={src}
            active={activeId === c.source_id}
            scrollTargetRef={(el: HTMLDivElement | null) => {
              if (el) refs.current.set(c.source_id, el);
              else refs.current.delete(c.source_id);
            }}
          />
        );
      })}
    </aside>
  );
}
