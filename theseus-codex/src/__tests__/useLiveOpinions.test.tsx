import { afterEach, describe, expect, it, vi } from "vitest";
import type { PublicOpinion } from "@/lib/currentsTypes";

function opinion(id: string, headline = id): PublicOpinion {
  return {
    id,
    organization_id: "org-1",
    event_id: `event-${id}`,
    stance: "complicates",
    confidence: 0.72,
    headline,
    body_markdown: `Body for ${headline}`,
    uncertainty_notes: [],
    topic_hint: "markets",
    model_name: "test-model",
    generated_at: "2026-04-29T12:00:00.000Z",
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: null,
    citations: [],
  };
}

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onopen: ((event: Event) => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
  }

  emitOpen() {
    this.onopen?.(new Event("open"));
  }

  emitMessage(payload: PublicOpinion | string) {
    const data = typeof payload === "string" ? payload : JSON.stringify(payload);
    this.onmessage?.({ data } as MessageEvent<string>);
  }

  emitError() {
    this.onerror?.(new Event("error"));
  }
}

interface HookHarnessState {
  states: Array<{ opinions: PublicOpinion[]; connected: boolean }>;
  cleanup?: () => void;
}

function mockReactForHook(harness: HookHarnessState) {
  vi.doMock("react", () => ({
    useEffect: (effect: () => void | (() => void)) => {
      harness.cleanup = effect() || undefined;
    },
    useReducer: (
      reducer: (
        state: { opinions: PublicOpinion[]; connected: boolean },
        action: unknown,
      ) => { opinions: PublicOpinion[]; connected: boolean },
      initialState: { opinions: PublicOpinion[]; connected: boolean },
    ) => {
      let current = initialState;
      harness.states.push(current);
      const dispatch = (action: unknown) => {
        current = reducer(current, action);
        harness.states.push(current);
      };
      return [current, dispatch] as const;
    },
    useRef: <T,>(current: T) => ({ current }),
  }));
}

describe("useLiveOpinions", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.doUnmock("react");
    vi.resetModules();
    FakeEventSource.instances = [];
  });

  it("prepends opinions, dedupes by id, and caps in-memory state at 200", async () => {
    const { liveOpinionsReducer } = await import("@/lib/useLiveOpinions");
    let state = liveOpinionsReducer(
      { opinions: [opinion("seed-a"), opinion("seed-b")], connected: true },
      { type: "opinion", payload: opinion("live") },
    );

    expect(state.opinions.map((item) => item.id)).toEqual([
      "live",
      "seed-a",
      "seed-b",
    ]);

    state = liveOpinionsReducer(state, {
      type: "opinion",
      payload: opinion("seed-a", "updated seed"),
    });

    expect(state.opinions.map((item) => item.id)).toEqual([
      "seed-a",
      "live",
      "seed-b",
    ]);
    expect(state.opinions[0].headline).toBe("updated seed");

    const many = Array.from({ length: 205 }, (_, index) =>
      opinion(`seed-${index}`),
    );
    state = liveOpinionsReducer(
      { opinions: many, connected: false },
      { type: "opinion", payload: opinion("newest") },
    );

    expect(state.opinions).toHaveLength(200);
    expect(state.opinions[0].id).toBe("newest");
    expect(state.opinions[199].id).toBe("seed-198");
  });

  it("connects to the SSE endpoint and keeps seed data visible while messages arrive", async () => {
    const harness: HookHarnessState = { states: [] };
    mockReactForHook(harness);
    vi.stubGlobal("EventSource", FakeEventSource);

    const { useLiveOpinions } = await import("@/lib/useLiveOpinions");
    const initial = useLiveOpinions([opinion("seed")]);

    expect(initial.opinions.map((item) => item.id)).toEqual(["seed"]);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe("/api/currents/stream");

    FakeEventSource.instances[0].emitOpen();
    expect(harness.states.at(-1)?.connected).toBe(true);

    FakeEventSource.instances[0].emitMessage(opinion("live"));
    expect(harness.states.at(-1)?.opinions.map((item) => item.id)).toEqual([
      "live",
      "seed",
    ]);

    FakeEventSource.instances[0].emitMessage("{not json");
    expect(harness.states.at(-1)?.opinions.map((item) => item.id)).toEqual([
      "live",
      "seed",
    ]);

    harness.cleanup?.();
    expect(FakeEventSource.instances[0].closed).toBe(true);
  });

  it("reconnects with doubled backoff and resets the delay after a successful open", async () => {
    vi.useFakeTimers();
    const harness: HookHarnessState = { states: [] };
    mockReactForHook(harness);
    vi.stubGlobal("EventSource", FakeEventSource);

    const { useLiveOpinions } = await import("@/lib/useLiveOpinions");
    useLiveOpinions([]);

    FakeEventSource.instances[0].emitError();
    expect(FakeEventSource.instances[0].closed).toBe(true);
    expect(harness.states.at(-1)?.connected).toBe(false);

    vi.advanceTimersByTime(999);
    expect(FakeEventSource.instances).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(FakeEventSource.instances).toHaveLength(2);

    FakeEventSource.instances[1].emitError();
    vi.advanceTimersByTime(1_999);
    expect(FakeEventSource.instances).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(FakeEventSource.instances).toHaveLength(3);

    FakeEventSource.instances[2].emitOpen();
    FakeEventSource.instances[2].emitError();
    vi.advanceTimersByTime(999);
    expect(FakeEventSource.instances).toHaveLength(3);
    vi.advanceTimersByTime(1);
    expect(FakeEventSource.instances).toHaveLength(4);

    harness.cleanup?.();
  });
});
