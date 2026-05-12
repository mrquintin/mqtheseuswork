"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { CurrentsHealth } from "@/lib/currentsApi";
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
  health: CurrentsHealth | null;
  seed: PublicOpinion[];
  detailBasePath?: string;
  /**
   * Founder/operator views surface backend reasons aloud (disconnected feed,
   * disabled-ingestion banner). Public views stay calm and hide them.
   */
  diagnostic?: boolean;
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
        : "The firm is reading public signals. Nothing significant enough to publish yet — opinions appear here when a real-world post crosses the firm's significance and relevance floors."}
    </div>
  );
}

function DisabledBanner({
  health,
  diagnostic,
}: {
  health: CurrentsHealth | null;
  diagnostic: boolean;
}) {
  if (!diagnostic) return null;
  if (!health || health.disabled_reasons.length === 0) return null;
  const reasons = health.disabled_reasons.join(", ");
  return (
    <div
      role="status"
      style={{
        background: "rgba(172, 54, 37, 0.13)",
        border: "1px solid rgba(255, 111, 82, 0.55)",
        borderLeft: "4px solid var(--currents-stance-disagrees)",
        borderRadius: "6px",
        color: "var(--currents-parchment)",
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: "0.78rem",
        lineHeight: 1.55,
        marginBottom: "1rem",
        padding: "0.75rem 0.9rem",
      }}
    >
      Currents ingestion disabled — set X_BEARER_TOKEN. If discovery is disabled,
      also set CURRENTS_X_CURATED_ACCOUNTS or CURRENTS_X_SEARCH_QUERIES.
      <span style={{ color: "var(--currents-parchment-dim)" }}>
        {" "}
        Reason: {reasons}.
      </span>
    </div>
  );
}

export default function FeedClient({
  health,
  seed,
  detailBasePath = "/currents",
  diagnostic = false,
}: FeedClientProps) {
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
      <DisabledBanner health={health} diagnostic={diagnostic} />
      <LiveBanner connected={connected} diagnostic={diagnostic} />
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
        <TopicClusters
          basePath={pathname}
          detailBasePath={detailBasePath}
          filter={filter}
          opinions={filteredOpinions}
        />
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
              detailBasePath={detailBasePath}
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
