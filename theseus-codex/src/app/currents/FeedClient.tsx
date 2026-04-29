"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { PublicOpinion } from "@/lib/currentsTypes";
import {
  filterToParams,
  hasActiveMatchFilter,
  matches,
  paramsToFilter,
  type Filter,
} from "@/lib/filterMatch";
import { useLiveOpinions } from "@/lib/useLiveOpinions";

import FilterBar from "./FilterBar";
import LiveBanner from "./LiveBanner";
import OpinionCard from "./OpinionCard";
import TopicClusters from "./TopicClusters";

interface FeedClientProps {
  seed: PublicOpinion[];
}

function latestOpinionAt(opinions: PublicOpinion[]): string | null {
  let latest: string | null = null;
  let latestTime = -Infinity;

  for (const opinion of opinions) {
    const time = new Date(opinion.generated_at).getTime();
    if (Number.isFinite(time) && time > latestTime) {
      latestTime = time;
      latest = opinion.generated_at;
    }
  }

  return latest;
}

function matchFilterKey(filter: Filter): string {
  return filterToParams({ ...filter, view: "feed" }).toString();
}

function EmptyFeedMessage({ filtered }: { filtered: boolean }) {
  return (
    <div
      style={{
        background: "rgba(232, 225, 211, 0.03)",
        border: "1px solid var(--currents-border)",
        borderLeft: "4px solid var(--currents-stance-abstained)",
        borderRadius: "6px",
        color: "var(--currents-parchment-dim)",
        padding: "1rem",
      }}
    >
      {filtered
        ? "No opinions match these filters."
        : "No opinions yet. The firm abstains when its knowledge base does not support a position."}
    </div>
  );
}

export default function FeedClient({ seed }: FeedClientProps) {
  const seedIds = useRef(new Set(seed.map((opinion) => opinion.id)));
  const seenOpinionIds = useRef(new Set(seed.map((opinion) => opinion.id)));
  const activeFilterKey = useRef<string | null>(null);
  const [otherFilterCount, setOtherFilterCount] = useState(0);
  const pathname = usePathname() || "/currents";
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchParamString = searchParams.toString();
  const { opinions, connected } = useLiveOpinions(seed);
  const filter = useMemo(
    () => paramsToFilter(searchParamString),
    [searchParamString],
  );
  const filteredOpinions = useMemo(
    () => opinions.filter((opinion) => matches(opinion, filter)),
    [filter, opinions],
  );
  const lastOpinionAt = useMemo(() => latestOpinionAt(opinions), [opinions]);
  const activeCriteria = hasActiveMatchFilter(filter);

  useEffect(() => {
    const nextFilterKey = matchFilterKey(filter);

    if (activeFilterKey.current !== nextFilterKey) {
      activeFilterKey.current = nextFilterKey;
      seenOpinionIds.current = new Set(opinions.map((opinion) => opinion.id));
      setOtherFilterCount(0);
      return;
    }

    if (!activeCriteria) {
      seenOpinionIds.current = new Set(opinions.map((opinion) => opinion.id));
      setOtherFilterCount(0);
      return;
    }

    let hiddenArrivalCount = 0;

    for (const opinion of opinions) {
      if (seenOpinionIds.current.has(opinion.id)) continue;
      seenOpinionIds.current.add(opinion.id);
      if (!matches(opinion, filter)) hiddenArrivalCount += 1;
    }

    if (hiddenArrivalCount) {
      setOtherFilterCount((count) => count + hiddenArrivalCount);
    }
  }, [activeCriteria, filter, opinions]);

  const clearFilters = () => {
    setOtherFilterCount(0);
    router.replace(pathname, { scroll: false });
  };

  return (
    <section aria-label="Current-events opinions">
      <LiveBanner connected={connected} lastOpinionAt={lastOpinionAt} />
      <FilterBar opinions={opinions} />

      {otherFilterCount ? (
        <button
          onClick={clearFilters}
          style={{
            background: "rgba(212, 160, 23, 0.12)",
            border: "1px solid var(--currents-gold)",
            borderRadius: "6px",
            color: "var(--currents-gold)",
            cursor: "pointer",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.78rem",
            letterSpacing: "0.03em",
            marginBottom: "1rem",
            padding: "0.65rem 0.8rem",
            width: "100%",
          }}
          type="button"
        >
          {otherFilterCount} new items match other filters
        </button>
      ) : null}

      {filteredOpinions.length && filter.view === "clusters" ? (
        <TopicClusters filter={filter} opinions={filteredOpinions} />
      ) : filteredOpinions.length ? (
        <div
          aria-live="polite"
          style={{
            display: "grid",
            gap: "0.9rem",
          }}
        >
          {filteredOpinions.map((opinion) => (
            <OpinionCard
              key={opinion.id}
              opinion={opinion}
              className={seedIds.current.has(opinion.id) ? undefined : "currents-fade-in"}
            />
          ))}
        </div>
      ) : (
        <EmptyFeedMessage filtered={opinions.length > 0} />
      )}
    </section>
  );
}
