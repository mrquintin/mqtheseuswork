"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { PublicOpinion } from "@/lib/currentsTypes";
import {
  STANCES,
  filterToParams,
  opinionTopicId,
  paramsToFilter,
  type Filter,
  type SincePreset,
  type StanceFilter,
  type ViewMode,
} from "@/lib/filterMatch";

export const FILTER_SEARCH_DEBOUNCE_MS = 250;

interface FilterRouter {
  replace(href: string, options?: { scroll?: boolean }): void;
}

type TimerId = ReturnType<typeof setTimeout>;

const allSincePresets: SincePreset[] = ["all", "1h", "6h", "24h", "7d"];

const sinceLabels: Record<SincePreset, string> = {
  all: "All",
  "1h": "1h",
  "6h": "6h",
  "24h": "24h",
  "7d": "7d",
};

const viewLabels: Record<ViewMode, string> = {
  feed: "Feed",
  clusters: "Clusters",
};

const barStyle: CSSProperties = {
  background: "rgba(232, 225, 211, 0.035)",
  border: "1px solid var(--currents-border)",
  borderRadius: "6px",
  display: "grid",
  gap: "0.85rem",
  marginBottom: "1rem",
  padding: "0.9rem",
};

const controlGridStyle: CSSProperties = {
  display: "grid",
  gap: "0.75rem",
  gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 13rem), 1fr))",
};

const groupStyle: CSSProperties = {
  display: "grid",
  gap: "0.35rem",
};

const labelStyle: CSSProperties = {
  color: "var(--currents-muted)",
  fontSize: "0.68rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const rowStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "0.45rem",
};

const inputStyle: CSSProperties = {
  background: "rgba(20, 18, 16, 0.86)",
  border: "1px solid var(--currents-border)",
  borderRadius: "4px",
  color: "var(--currents-parchment)",
  fontFamily: "inherit",
  fontSize: "0.95rem",
  minHeight: "2.45rem",
  padding: "0.55rem 0.7rem",
  width: "100%",
};

const chipBaseStyle: CSSProperties = {
  border: "1px solid var(--currents-border)",
  borderRadius: "999px",
  cursor: "pointer",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.72rem",
  letterSpacing: "0.04em",
  lineHeight: 1,
  minHeight: "2rem",
  padding: "0.46rem 0.65rem",
  textTransform: "uppercase",
};

export function filterHref(pathname: string, filter: Filter): string {
  const params = filterToParams(filter);
  const query = params.toString();
  return query ? `${pathname}?${query}` : pathname;
}

export function replaceFilterUrl(
  router: FilterRouter,
  pathname: string,
  filter: Filter,
) {
  router.replace(filterHref(pathname || "/currents", filter), { scroll: false });
}

export function toggleStanceFilter(
  filter: Filter,
  stance: StanceFilter,
): Filter {
  const active = filter.stance.includes(stance);
  const nextStance = active
    ? filter.stance.filter((item) => item !== stance)
    : STANCES.filter((item) => item === stance || filter.stance.includes(item));

  return { ...filter, stance: nextStance };
}

export function topicOptions(
  opinions: PublicOpinion[],
  activeTopic: string | null,
): string[] {
  const topics = new Set<string>();

  for (const opinion of opinions) {
    topics.add(opinionTopicId(opinion));
  }

  if (activeTopic) topics.add(activeTopic);

  return Array.from(topics).sort((a, b) => a.localeCompare(b));
}

export function createDebouncedSearchUpdater(
  getFilter: () => Filter,
  replaceFilter: (filter: Filter) => void,
  delayMs = FILTER_SEARCH_DEBOUNCE_MS,
) {
  let timeoutId: TimerId | null = null;

  return {
    cancel() {
      if (timeoutId !== null) clearTimeout(timeoutId);
      timeoutId = null;
    },
    queue(q: string) {
      if (timeoutId !== null) clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        timeoutId = null;
        replaceFilter({ ...getFilter(), q });
      }, delayMs);
    },
  };
}

function chipStyle(active: boolean, accent = "var(--currents-gold)"): CSSProperties {
  return {
    ...chipBaseStyle,
    background: active ? "rgba(212, 160, 23, 0.16)" : "transparent",
    borderColor: active ? accent : "var(--currents-border)",
    color: active ? accent : "var(--currents-parchment-dim)",
  };
}

interface FilterBarViewProps {
  filter: Filter;
  searchValue: string;
  topics: string[];
  onFilterChange: (filter: Filter) => void;
  onSearchChange: (value: string) => void;
}

export function FilterBarView({
  filter,
  searchValue,
  topics,
  onFilterChange,
  onSearchChange,
}: FilterBarViewProps) {
  return (
    <section aria-label="Filter currents" style={barStyle}>
      <div style={controlGridStyle}>
        <label style={groupStyle}>
          <span style={labelStyle}>Search</span>
          <input
            aria-label="Search opinions"
            onChange={(event) => onSearchChange(event.currentTarget.value)}
            placeholder="Headline, body, topic"
            style={inputStyle}
            type="search"
            value={searchValue}
          />
        </label>

        <label style={groupStyle}>
          <span style={labelStyle}>Topic</span>
          <select
            aria-label="Topic"
            onChange={(event) =>
              onFilterChange({
                ...filter,
                topic: event.currentTarget.value || null,
              })
            }
            style={inputStyle}
            value={filter.topic || ""}
          >
            <option value="">All topics</option>
            {topics.map((topic) => (
              <option key={topic} value={topic}>
                {topic}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div style={rowStyle}>
        {STANCES.map((stance) => (
          <button
            aria-pressed={filter.stance.includes(stance)}
            key={stance}
            onClick={() => onFilterChange(toggleStanceFilter(filter, stance))}
            style={chipStyle(
              filter.stance.includes(stance),
              `var(--currents-stance-${stance})`,
            )}
            type="button"
          >
            {stance}
          </button>
        ))}
      </div>

      <div style={rowStyle}>
        {allSincePresets.map((since) => (
          <button
            aria-pressed={filter.since === since}
            key={since}
            onClick={() => onFilterChange({ ...filter, since })}
            style={chipStyle(filter.since === since)}
            type="button"
          >
            {sinceLabels[since]}
          </button>
        ))}
      </div>

      <div style={rowStyle}>
        {(["feed", "clusters"] as ViewMode[]).map((view) => (
          <button
            aria-pressed={filter.view === view}
            key={view}
            onClick={() => onFilterChange({ ...filter, view })}
            style={chipStyle(filter.view === view)}
            type="button"
          >
            {viewLabels[view]}
          </button>
        ))}
      </div>
    </section>
  );
}

interface FilterBarProps {
  opinions: PublicOpinion[];
}

export default function FilterBar({ opinions }: FilterBarProps) {
  const pathname = usePathname() || "/currents";
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchParamString = searchParams.toString();
  const filter = useMemo(
    () => paramsToFilter(searchParamString),
    [searchParamString],
  );
  const filterRef = useRef(filter);
  const [searchValue, setSearchValue] = useState(filter.q);

  filterRef.current = filter;

  const replaceFilter = useCallback(
    (nextFilter: Filter) => replaceFilterUrl(router, pathname, nextFilter),
    [pathname, router],
  );
  const searchUpdater = useMemo(
    () => createDebouncedSearchUpdater(() => filterRef.current, replaceFilter),
    [replaceFilter],
  );
  const topics = useMemo(
    () => topicOptions(opinions, filter.topic),
    [opinions, filter.topic],
  );

  useEffect(() => () => searchUpdater.cancel(), [searchUpdater]);

  useEffect(() => {
    setSearchValue(filter.q);
    searchUpdater.cancel();
  }, [filter.q, searchUpdater]);

  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchValue(value);
      searchUpdater.queue(value);
    },
    [searchUpdater],
  );

  return (
    <FilterBarView
      filter={filter}
      onFilterChange={replaceFilter}
      onSearchChange={handleSearchChange}
      searchValue={searchValue}
      topics={topics}
    />
  );
}
