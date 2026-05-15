"use client";

import { useEffect, useState } from "react";

import LineageTimeline from "@/components/LineageTimeline";
import type { Lineage } from "@/lib/lineage";

/**
 * Founder-side lineage panel.
 *
 * Fetches the timeline from `/api/conclusion/[id]/lineage` and hands it
 * to `LineageTimeline` — the v2 layered, virtualised swim-lane view.
 * v1 rendered a flat <ol> with a scrub slider, which was unreadable
 * once a conclusion accumulated 30+ events; the lane filtering, event
 * grouping, and virtualisation now live in `LineageTimeline`.
 *
 * Why client-side fetching: the panel is a tab inside the conclusion
 * detail page, and the parent page is server-rendered with a small
 * payload. Loading the lineage lazily keeps the initial paint small for
 * conclusions with hundreds of nodes.
 */

type Props = {
  conclusionId: string;
};

export default function LineagePanel({ conclusionId }: Props) {
  const [data, setData] = useState<Lineage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setData(null);
    fetch(`/api/conclusion/${conclusionId}/lineage`, {
      headers: { Accept: "application/json" },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as Lineage;
      })
      .then((l) => {
        if (cancelled) return;
        setData(l);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [conclusionId]);

  if (error) {
    return (
      <p className="mono" style={{ color: "var(--ember)" }}>
        Lineage unavailable: {error}
      </p>
    );
  }
  if (!data) {
    return (
      <p className="mono" style={{ color: "var(--parchment-dim)" }}>
        Loading lineage…
      </p>
    );
  }

  return (
    <div>
      <LineageTimeline lineage={data} />
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
        Assembled {new Date(data.assembledAt).toLocaleString()}
      </p>
    </div>
  );
}
