"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useLiveOpinions } from "@/lib/useLiveOpinions";
import { listCurrents } from "@/lib/currentsApi";
import {
  filterToParams,
  matches,
  paramsToFilter,
  type FilterState,
} from "@/lib/filterMatch";
import type { PublicOpinion } from "@/lib/currentsTypes";
import { OpinionCard } from "./OpinionCard";
import { LiveBanner } from "./LiveBanner";
import { FilterBar } from "./FilterBar";
import { TopicClusters } from "./TopicClusters";

export function FeedClient({
  seed,
  initialFilter: _initialFilter,
}: {
  seed: PublicOpinion[];
  initialFilter: FilterState;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const filter = useMemo(
    () => paramsToFilter(sp ?? new URLSearchParams()),
    [sp],
  );

  const [opinions, setOpinions] = useState<PublicOpinion[]>(seed);
  const [hiddenNewCount, setHiddenNewCount] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // Ref keeps the callback stable across renders while still reading the
  // latest filter when live opinions arrive.
  const filterRef = useRef(filter);
  filterRef.current = filter;

  const onNewOpinion = useCallback((op: PublicOpinion) => {
    if (!matches(op, filterRef.current)) {
      setHiddenNewCount((n) => n + 1);
    }
  }, []);

  const { opinions: liveOpinions, connected } = useLiveOpinions(opinions, {
    onNewOpinion,
  });

  // When any server-affecting filter changes, re-seed the first page from
  // the backend. The SSE stream keeps running independently.
  const lastFilterKey = useRef(filterToParams(filter).toString());
  useEffect(() => {
    const key = filterToParams(filter).toString();
    if (key === lastFilterKey.current) return;
    lastFilterKey.current = key;
    setHiddenNewCount(0);
    setCursor(null);
    listCurrents({
      limit: 20,
      topic: filter.topic ?? undefined,
      stance: filter.stance ?? undefined,
      since: filter.since ?? undefined,
    })
      .then((resp) => {
        setOpinions(resp.items);
        setCursor(resp.next_cursor ?? null);
      })
      .catch((err) => {
        console.error("filter_refetch_failed", err);
      });
  }, [filter.topic, filter.stance, filter.since, filter.q, filter.view, filter]);

  const visibleOpinions = useMemo(
    () => liveOpinions.filter((op) => matches(op, filter)),
    [liveOpinions, filter],
  );

  const topics = useMemo(() => {
    const seen = new Set<string>();
    for (const op of liveOpinions) {
      if (op.topic_hint) seen.add(op.topic_hint);
    }
    return [...seen].sort();
  }, [liveOpinions]);

  const lastOpinionAt = liveOpinions[0]?.generated_at ?? null;

  const clearFilters = useCallback(() => {
    router.replace(pathname, { scroll: false });
    setHiddenNewCount(0);
  }, [router, pathname]);

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const resp = await listCurrents({
        cursor,
        limit: 20,
        topic: filter.topic ?? undefined,
        stance: filter.stance ?? undefined,
        since: filter.since ?? undefined,
      });
      setOpinions((prev) => {
        const seen = new Set(prev.map((o) => o.id));
        const merged = [...prev];
        for (const o of resp.items) if (!seen.has(o.id)) merged.push(o);
        return merged;
      });
      setCursor(resp.next_cursor ?? null);
    } catch (err) {
      console.error("load_more_failed", err);
    } finally {
      setLoadingMore(false);
    }
  }, [cursor, loadingMore, filter.topic, filter.stance, filter.since]);

  return (
    <section style={{ marginTop: "1.5rem" }}>
      <LiveBanner connected={connected} lastOpinionAt={lastOpinionAt} />
      <FilterBar topics={topics} />
      {hiddenNewCount > 0 ? (
        <div
          data-testid="hidden-new-banner"
          style={{
            border: "1px dashed var(--currents-border)",
            padding: "0.55rem 0.8rem",
            margin: "0.5rem 0 1rem",
            color: "var(--currents-parchment-dim)",
            fontSize: "0.78rem",
            fontStyle: "italic",
          }}
        >
          {hiddenNewCount} new {hiddenNewCount === 1 ? "item" : "items"} match
          other filters —{" "}
          <button
            type="button"
            onClick={clearFilters}
            style={{
              color: "var(--currents-gold)",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              textDecoration: "underline",
              font: "inherit",
              padding: 0,
            }}
          >
            clear to show
          </button>
        </div>
      ) : null}
      {visibleOpinions.length === 0 ? (
        <EmptyState />
      ) : filter.view === "by-topic" ? (
        <TopicClusters opinions={visibleOpinions} />
      ) : (
        visibleOpinions.map((op) => <OpinionCard key={op.id} op={op} />)
      )}
      {cursor ? (
        <div style={{ textAlign: "center", margin: "1.5rem 0" }}>
          <button
            type="button"
            onClick={loadMore}
            disabled={loadingMore}
            data-testid="load-more"
            style={{
              background: "transparent",
              border: "1px solid var(--currents-border)",
              color: "var(--currents-parchment-dim)",
              padding: "0.5rem 1.1rem",
              fontSize: "0.78rem",
              cursor: loadingMore ? "not-allowed" : "pointer",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            {loadingMore ? "loading…" : "load older"}
          </button>
        </div>
      ) : null}
    </section>
  );
}

function EmptyState() {
  return (
    <div
      data-testid="empty-state"
      style={{
        padding: "3rem 1rem",
        textAlign: "center",
        fontStyle: "italic",
        color: "var(--currents-parchment-dim)",
        fontSize: "0.95rem",
        lineHeight: 1.6,
      }}
    >
      No opinions yet. The firm is watching, and will speak when its
      Noosphere supports a position.
    </div>
  );
}
