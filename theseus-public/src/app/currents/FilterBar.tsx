"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  filterToParams,
  paramsToFilter,
  type FilterState,
} from "@/lib/filterMatch";
import type { Stance } from "@/lib/currentsTypes";

const STANCES: { value: Stance; label: string }[] = [
  { value: "agrees", label: "agrees" },
  { value: "disagrees", label: "disagrees" },
  { value: "complicates", label: "complicates" },
  { value: "insufficient", label: "insufficient" },
];

const SINCE_PRESETS: { value: string; label: string; hours: number | null }[] =
  [
    { value: "", label: "any time", hours: null },
    { value: "1h", label: "1h", hours: 1 },
    { value: "24h", label: "24h", hours: 24 },
    { value: "7d", label: "7d", hours: 24 * 7 },
  ];

function presetToIso(hours: number | null): string | null {
  if (hours == null) return null;
  return new Date(Date.now() - hours * 3600 * 1000).toISOString();
}

function activePresetLabel(since: string | null): string {
  if (!since) return "";
  // Match whichever bucket the ISO falls into (within a minute of bucket start).
  const t = new Date(since).getTime();
  if (isNaN(t)) return "";
  const now = Date.now();
  const diffHours = (now - t) / (3600 * 1000);
  // Tolerant match: pick the closest preset.
  const candidates = SINCE_PRESETS.filter((p) => p.hours != null);
  let best: (typeof candidates)[number] | null = null;
  let bestDelta = Infinity;
  for (const c of candidates) {
    const d = Math.abs(diffHours - (c.hours ?? 0));
    if (d < bestDelta) {
      bestDelta = d;
      best = c;
    }
  }
  // Only treat as the preset if within 5% tolerance on the hours scale.
  if (best && bestDelta / (best.hours ?? 1) < 0.05) return best.value;
  return "";
}

export function FilterBar({ topics }: { topics: string[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const filter = useMemo(
    () => paramsToFilter(sp ?? new URLSearchParams()),
    [sp],
  );

  // Local buffered search input (debounced into URL).
  const [qDraft, setQDraft] = useState<string>(filter.q ?? "");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastPushedQRef = useRef<string | null>(filter.q);

  // Keep the draft aligned with URL changes that came from elsewhere (back
  // button, clear-filters button, etc.) without stomping in-progress typing.
  useEffect(() => {
    if ((filter.q ?? "") !== (lastPushedQRef.current ?? "")) {
      setQDraft(filter.q ?? "");
      lastPushedQRef.current = filter.q;
    }
  }, [filter.q]);

  const push = (next: FilterState) => {
    const qs = filterToParams(next).toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const onSearchChange = (value: string) => {
    setQDraft(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const next: FilterState = { ...filter, q: value.trim() || null };
      lastPushedQRef.current = next.q;
      push(next);
    }, 250);
  };

  const onTopicChange = (value: string) => {
    push({ ...filter, topic: value || null });
  };

  const onStanceClick = (stance: Stance) => {
    push({
      ...filter,
      stance: filter.stance === stance ? null : stance,
    });
  };

  const onSinceClick = (presetValue: string, hours: number | null) => {
    const iso = presetToIso(hours);
    // If already active, clear.
    if ((activePresetLabel(filter.since) || "") === presetValue && presetValue)
      push({ ...filter, since: null });
    else push({ ...filter, since: iso });
  };

  const onViewToggle = () => {
    push({
      ...filter,
      view: filter.view === "chronological" ? "by-topic" : "chronological",
    });
  };

  const activeSince = activePresetLabel(filter.since);

  return (
    <div
      data-testid="filter-bar"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 10,
        background: "var(--currents-bg)",
        borderBottom: "1px solid var(--currents-border)",
        padding: "0.7rem 0.25rem",
        margin: "0 0 1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.55rem",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: "0.6rem",
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <input
          type="search"
          aria-label="Search opinions"
          placeholder="search opinions…"
          value={qDraft}
          onChange={(e) => onSearchChange(e.target.value)}
          data-testid="filter-search"
          style={{
            flex: "1 1 200px",
            minWidth: "180px",
            background: "var(--currents-surface)",
            border: "1px solid var(--currents-border)",
            color: "var(--currents-parchment)",
            padding: "0.4rem 0.65rem",
            borderRadius: "6px",
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: "0.82rem",
          }}
        />
        <select
          aria-label="Topic"
          value={filter.topic ?? ""}
          onChange={(e) => onTopicChange(e.target.value)}
          data-testid="filter-topic"
          style={{
            background: "var(--currents-surface)",
            border: "1px solid var(--currents-border)",
            color: "var(--currents-parchment)",
            padding: "0.4rem 0.55rem",
            borderRadius: "6px",
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: "0.82rem",
            minWidth: "140px",
          }}
        >
          <option value="">all topics</option>
          {topics.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={onViewToggle}
          data-testid="filter-view-toggle"
          aria-pressed={filter.view === "by-topic"}
          style={{
            background: "transparent",
            border: "1px solid var(--currents-border)",
            color: "var(--currents-parchment-dim)",
            padding: "0.35rem 0.7rem",
            borderRadius: "6px",
            fontSize: "0.72rem",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            cursor: "pointer",
          }}
        >
          {filter.view === "by-topic" ? "by topic" : "chronological"}
        </button>
      </div>
      <div
        style={{
          display: "flex",
          gap: "0.4rem",
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            fontSize: "0.68rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--currents-parchment-dim)",
            marginRight: "0.3rem",
          }}
        >
          stance
        </span>
        {STANCES.map((s) => {
          const active = filter.stance === s.value;
          return (
            <button
              key={s.value}
              type="button"
              onClick={() => onStanceClick(s.value)}
              data-testid={`filter-stance-${s.value}`}
              data-active={active ? "true" : "false"}
              aria-pressed={active}
              style={{
                background: active
                  ? "var(--currents-gold)"
                  : "transparent",
                color: active
                  ? "var(--currents-bg)"
                  : "var(--currents-parchment-dim)",
                border: "1px solid var(--currents-border)",
                padding: "0.22rem 0.65rem",
                borderRadius: "999px",
                fontSize: "0.72rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                cursor: "pointer",
              }}
            >
              {s.label}
            </button>
          );
        })}
        <span
          style={{
            fontSize: "0.68rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--currents-parchment-dim)",
            margin: "0 0.3rem 0 0.6rem",
          }}
        >
          since
        </span>
        {SINCE_PRESETS.map((p) => {
          const active =
            (p.value === "" && !filter.since) ||
            (p.value !== "" && activeSince === p.value);
          return (
            <button
              key={p.value || "any"}
              type="button"
              onClick={() => onSinceClick(p.value, p.hours)}
              data-testid={`filter-since-${p.value || "any"}`}
              data-active={active ? "true" : "false"}
              aria-pressed={active}
              style={{
                background: active
                  ? "var(--currents-gold)"
                  : "transparent",
                color: active
                  ? "var(--currents-bg)"
                  : "var(--currents-parchment-dim)",
                border: "1px solid var(--currents-border)",
                padding: "0.22rem 0.6rem",
                borderRadius: "999px",
                fontSize: "0.72rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                cursor: "pointer",
              }}
            >
              {p.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
