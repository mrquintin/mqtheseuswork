import { describe, expect, it } from "vitest";
import {
  EMPTY_FILTER,
  filterToParams,
  matches,
  paramsToFilter,
  type FilterState,
} from "@/lib/filterMatch";
import type { PublicOpinion } from "@/lib/currentsTypes";

function makeOpinion(overrides: Partial<PublicOpinion> = {}): PublicOpinion {
  return {
    id: "op-1",
    event_id: "evt-1",
    event_source_url: "https://x.example/status/1",
    event_author_handle: "someone",
    event_captured_at: "2026-04-20T00:00:00Z",
    topic_hint: "markets",
    stance: "agrees",
    confidence: 0.5,
    headline: "The firm considers a cascade",
    body_markdown: "A body with a SEARCHABLE needle inside.",
    uncertainty_notes: [],
    generated_at: "2026-04-20T12:00:00Z",
    citations: [],
    revoked: false,
    ...overrides,
  };
}

describe("matches", () => {
  it("returns true for the empty filter", () => {
    expect(matches(makeOpinion(), EMPTY_FILTER)).toBe(true);
  });

  it("applies the topic filter (exact match, case-sensitive)", () => {
    const op = makeOpinion({ topic_hint: "markets" });
    expect(matches(op, { ...EMPTY_FILTER, topic: "markets" })).toBe(true);
    expect(matches(op, { ...EMPTY_FILTER, topic: "politics" })).toBe(false);
  });

  it("rejects when topic filter set but opinion has null topic", () => {
    const op = makeOpinion({ topic_hint: null });
    expect(matches(op, { ...EMPTY_FILTER, topic: "markets" })).toBe(false);
  });

  it("applies the stance filter", () => {
    const op = makeOpinion({ stance: "complicates" });
    expect(matches(op, { ...EMPTY_FILTER, stance: "complicates" })).toBe(true);
    expect(matches(op, { ...EMPTY_FILTER, stance: "agrees" })).toBe(false);
  });

  it("applies the since filter using ISO string comparison", () => {
    const op = makeOpinion({ generated_at: "2026-04-20T12:00:00Z" });
    expect(
      matches(op, { ...EMPTY_FILTER, since: "2026-04-20T11:00:00Z" }),
    ).toBe(true);
    expect(
      matches(op, { ...EMPTY_FILTER, since: "2026-04-20T13:00:00Z" }),
    ).toBe(false);
  });

  it("does a case-insensitive substring search on headline+body", () => {
    const op = makeOpinion({
      headline: "Hello World",
      body_markdown: "Some body with Needle in it",
    });
    expect(matches(op, { ...EMPTY_FILTER, q: "needle" })).toBe(true);
    expect(matches(op, { ...EMPTY_FILTER, q: "WORLD" })).toBe(true);
    expect(matches(op, { ...EMPTY_FILTER, q: "absent" })).toBe(false);
  });

  it("AND-combines all active filters", () => {
    const op = makeOpinion({
      topic_hint: "markets",
      stance: "agrees",
      generated_at: "2026-04-20T12:00:00Z",
      headline: "needle here",
      body_markdown: "",
    });
    const good: FilterState = {
      topic: "markets",
      stance: "agrees",
      since: "2026-04-20T11:00:00Z",
      q: "needle",
      view: "chronological",
    };
    expect(matches(op, good)).toBe(true);

    // Flip any one dimension and the match should fail.
    expect(matches(op, { ...good, stance: "disagrees" })).toBe(false);
    expect(matches(op, { ...good, topic: "other" })).toBe(false);
    expect(matches(op, { ...good, since: "2026-04-20T13:00:00Z" })).toBe(false);
    expect(matches(op, { ...good, q: "absent" })).toBe(false);
  });
});

describe("filterToParams / paramsToFilter", () => {
  it("produces an empty query string for EMPTY_FILTER", () => {
    expect(filterToParams(EMPTY_FILTER).toString()).toBe("");
  });

  it("round-trips through URLSearchParams", () => {
    const original: FilterState = {
      topic: "markets",
      stance: "disagrees",
      q: "hello world",
      since: "2026-04-20T11:00:00Z",
      view: "by-topic",
    };
    const qs = filterToParams(original);
    const parsed = paramsToFilter(qs);
    expect(parsed).toEqual(original);
  });

  it("round-trips a partial filter", () => {
    const partial: FilterState = {
      topic: null,
      stance: "agrees",
      q: null,
      since: null,
      view: "chronological",
    };
    const qs = filterToParams(partial);
    expect(qs.toString()).toBe("stance=agrees");
    expect(paramsToFilter(qs)).toEqual(partial);
  });

  it("parses a plain Record<string,string|undefined>", () => {
    const obj = { topic: "markets", view: "by-topic" };
    const parsed = paramsToFilter(obj);
    expect(parsed.topic).toBe("markets");
    expect(parsed.view).toBe("by-topic");
    expect(parsed.stance).toBeNull();
  });

  it("defaults view to chronological for unknown values", () => {
    const parsed = paramsToFilter({ view: "nonsense" });
    expect(parsed.view).toBe("chronological");
  });

  it("drops an unknown stance value", () => {
    const parsed = paramsToFilter({ stance: "bogus" });
    expect(parsed.stance).toBeNull();
  });
});
