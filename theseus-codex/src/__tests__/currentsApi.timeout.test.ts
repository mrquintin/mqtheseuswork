import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Build-time hangs on `/currents`-style pages were caused by the
 * Currents proxy waiting on an upstream that never responded — Vercel's
 * 524s would propagate into the page render and fail the deploy. The
 * helper now applies a bounded AbortSignal timeout so a slow / hung
 * backend produces a normal rejection that the page can fall back from.
 */
describe("currents API proxy timeout", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("CURRENTS_API_URL", "http://backend.test");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("aborts the upstream fetch when timeoutMs elapses", async () => {
    const fetchMock = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) => {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(init.signal?.reason ?? new Error("aborted"));
          });
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    const { getCurrentsHealth } = await import("@/lib/currentsApi");

    const start = Date.now();
    await expect(
      getCurrentsHealth({ timeoutMs: 50 }),
    ).rejects.toBeDefined();
    const elapsed = Date.now() - start;

    expect(elapsed).toBeLessThan(1_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0][1];
    expect(init?.signal).toBeDefined();
  });

  it("does not abort when the upstream responds within the budget", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          x_bearer_present: true,
          curated_count: 0,
          search_count: 0,
          last_cycle_at: null,
          events_last_24h: 0,
          opinions_last_24h: 0,
          disabled_reasons: [],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { getCurrentsHealth } = await import("@/lib/currentsApi");
    const result = await getCurrentsHealth({ timeoutMs: 1_000 });
    expect(result.curated_count).toBe(0);
  });
});
