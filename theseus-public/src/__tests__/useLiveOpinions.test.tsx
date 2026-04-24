// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useLiveOpinions } from "@/lib/useLiveOpinions";
import type { PublicOpinion } from "@/lib/currentsTypes";

function makeOpinion(id: string, generatedAt = "2026-04-20T00:00:00Z"): PublicOpinion {
  return {
    id,
    event_id: `evt-${id}`,
    event_source_url: "https://x.example/status/1",
    event_author_handle: "author",
    event_captured_at: "2026-04-20T00:00:00Z",
    topic_hint: null,
    stance: "agrees",
    confidence: 0.5,
    headline: `h-${id}`,
    body_markdown: "b",
    uncertainty_notes: [],
    generated_at: generatedAt,
    citations: [],
    revoked: false,
  };
}

type Listener = (ev: MessageEvent) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  listeners: Record<string, Listener[]> = {};
  onopen: (() => void) | null = null;
  onerror: ((ev?: unknown) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, cb: Listener) {
    (this.listeners[name] ??= []).push(cb);
  }

  emitOpen() {
    this.onopen?.();
  }

  emitError() {
    this.onerror?.();
  }

  emitOpinion(data: unknown) {
    for (const cb of this.listeners["opinion"] || []) {
      cb({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  emitHeartbeat() {
    for (const cb of this.listeners["heartbeat"] || []) {
      cb({ data: "{}" } as MessageEvent);
    }
  }

  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useLiveOpinions", () => {
  it("seeds from initial prop", () => {
    const op1 = makeOpinion("op-1", "2026-04-20T00:00:02Z");
    const op2 = makeOpinion("op-2", "2026-04-20T00:00:01Z");
    const { result } = renderHook(() => useLiveOpinions([op1, op2]));
    expect(result.current.opinions).toHaveLength(2);
    expect(result.current.opinions.map((o) => o.id)).toEqual(["op-1", "op-2"]);
    expect(result.current.connected).toBe(false);
  });

  it("marks connected on open", () => {
    const { result } = renderHook(() => useLiveOpinions([]));
    const es = FakeEventSource.instances[0];
    expect(es).toBeDefined();
    act(() => {
      es.emitOpen();
    });
    expect(result.current.connected).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it("appends on new opinion event", () => {
    const { result } = renderHook(() => useLiveOpinions([]));
    const es = FakeEventSource.instances[0];
    const op = makeOpinion("op-new");
    act(() => {
      es.emitOpinion(op);
    });
    expect(result.current.opinions).toHaveLength(1);
    expect(result.current.opinions[0].id).toBe("op-new");
  });

  it("dedupes by id", () => {
    const { result } = renderHook(() => useLiveOpinions([]));
    const es = FakeEventSource.instances[0];
    const op = makeOpinion("op-dup");
    act(() => {
      es.emitOpinion(op);
    });
    act(() => {
      es.emitOpinion(op);
    });
    expect(result.current.opinions).toHaveLength(1);
  });

  it("ignores heartbeat events (state unchanged)", () => {
    const seed = makeOpinion("seed-1");
    const { result } = renderHook(() => useLiveOpinions([seed]));
    const es = FakeEventSource.instances[0];
    const before = result.current.opinions;
    act(() => {
      es.emitHeartbeat();
    });
    expect(result.current.opinions).toBe(before);
    expect(result.current.opinions).toHaveLength(1);
  });

  it("reconnects with exponential backoff on error", () => {
    renderHook(() => useLiveOpinions([]));
    expect(FakeEventSource.instances).toHaveLength(1);

    // First error -> 1000ms delay before reconnect.
    act(() => {
      FakeEventSource.instances[0].emitError();
    });
    expect(FakeEventSource.instances[0].closed).toBe(true);

    // Before timer fires, still only one instance.
    act(() => {
      vi.advanceTimersByTime(999);
    });
    expect(FakeEventSource.instances).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(FakeEventSource.instances).toHaveLength(2);

    // Second error -> 2000ms delay.
    act(() => {
      FakeEventSource.instances[1].emitError();
    });
    act(() => {
      vi.advanceTimersByTime(1999);
    });
    expect(FakeEventSource.instances).toHaveLength(2);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(FakeEventSource.instances).toHaveLength(3);

    // Third error -> 4000ms delay.
    act(() => {
      FakeEventSource.instances[2].emitError();
    });
    act(() => {
      vi.advanceTimersByTime(3999);
    });
    expect(FakeEventSource.instances).toHaveLength(3);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(FakeEventSource.instances).toHaveLength(4);
  });

  it("resets backoff counter after a successful open", () => {
    renderHook(() => useLiveOpinions([]));
    // Error once to bump retryRef to 1.
    act(() => {
      FakeEventSource.instances[0].emitError();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(FakeEventSource.instances).toHaveLength(2);

    // Open succeeds — retryRef resets.
    act(() => {
      FakeEventSource.instances[1].emitOpen();
    });

    // Next error should wait only 1000ms again, not 2000ms.
    act(() => {
      FakeEventSource.instances[1].emitError();
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(FakeEventSource.instances).toHaveLength(3);
  });
});
