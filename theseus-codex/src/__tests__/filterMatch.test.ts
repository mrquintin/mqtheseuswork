import { describe, expect, it } from "vitest";

import type { PublicOpinion } from "@/lib/currentsTypes";
import {
  DEFAULT_FILTER,
  filterToParams,
  matches,
  paramsToFilter,
  type Filter,
} from "@/lib/filterMatch";

function opinion(overrides: Partial<PublicOpinion> = {}): PublicOpinion {
  return {
    id: "opinion-1",
    organization_id: "org-1",
    event_id: "event-1",
    stance: "agrees",
    confidence: 0.82,
    headline: "Markets misread inflation",
    body_markdown: "The body discusses fiscal pressure and credibility.",
    uncertainty_notes: [],
    topic_hint: "markets",
    model_name: "test-model",
    generated_at: "2026-04-29T12:00:00.000Z",
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: null,
    citations: [],
    ...overrides,
  };
}

describe("filterMatch", () => {
  it("matches free-text search against headline, body, and topic", () => {
    const op = opinion();

    expect(matches(op, { ...DEFAULT_FILTER, q: "inflation" })).toBe(true);
    expect(matches(op, { ...DEFAULT_FILTER, q: "fiscal pressure" })).toBe(true);
    expect(matches(op, { ...DEFAULT_FILTER, q: "MARKETS" })).toBe(true);
    expect(matches(op, { ...DEFAULT_FILTER, q: "geopolitics" })).toBe(false);
  });

  it("matches exact topic ids", () => {
    const op = opinion({ topic_hint: "energy" });

    expect(matches(op, { ...DEFAULT_FILTER, topic: "energy" })).toBe(true);
    expect(matches(op, { ...DEFAULT_FILTER, topic: "Energy" })).toBe(false);
    expect(matches(op, { ...DEFAULT_FILTER, topic: "markets" })).toBe(false);
    expect(matches(op, { ...DEFAULT_FILTER, topic: null })).toBe(true);
  });

  it("matches stance lists and treats an empty stance list as all stances", () => {
    const op = opinion({ stance: "disagrees" });

    expect(matches(op, { ...DEFAULT_FILTER, stance: [] })).toBe(true);
    expect(matches(op, { ...DEFAULT_FILTER, stance: ["disagrees"] })).toBe(true);
    expect(matches(op, { ...DEFAULT_FILTER, stance: ["agrees"] })).toBe(false);
  });

  it("matches since presets against generated_at", () => {
    const now = new Date("2026-04-29T12:00:00.000Z");
    const ninetyMinutesOld = opinion({
      generated_at: "2026-04-29T10:30:00.000Z",
    });
    const old = opinion({ generated_at: "2026-04-20T12:00:00.000Z" });

    expect(matches(ninetyMinutesOld, { ...DEFAULT_FILTER, since: "1h" }, now)).toBe(
      false,
    );
    expect(matches(ninetyMinutesOld, { ...DEFAULT_FILTER, since: "6h" }, now)).toBe(
      true,
    );
    expect(matches(old, { ...DEFAULT_FILTER, since: "7d" }, now)).toBe(false);
    expect(matches(old, { ...DEFAULT_FILTER, since: "all" }, now)).toBe(true);
  });

  it("round-trips filters through URLSearchParams", () => {
    const filter: Filter = {
      q: "trade credibility",
      topic: "markets",
      stance: ["disagrees", "complicates"],
      since: "24h",
      view: "clusters",
    };

    expect(paramsToFilter(filterToParams(filter))).toEqual(filter);
    expect(filterToParams(DEFAULT_FILTER).toString()).toBe("");
  });

  it("parses repeated and comma-separated stance params", () => {
    const filter = paramsToFilter(
      "stance=agrees&stance=disagrees,complicates&stance=bogus",
    );

    expect(filter.stance).toEqual(["agrees", "disagrees", "complicates"]);
  });
});
