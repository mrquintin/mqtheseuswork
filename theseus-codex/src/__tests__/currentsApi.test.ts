import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.fn();

describe("currents API proxy helpers", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("CURRENTS_API_URL", "http://backend.test");
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("listCurrents issues correct query params", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const { listCurrents } = await import("@/lib/currentsApi");
    await listCurrents({
      since: "2026-04-29T00:00:00.000Z",
      until: new Date("2026-04-30T00:00:00.000Z"),
      topic: "ai",
      stance: "support",
      limit: 7,
    });

    const [url, init] = fetchMock.mock.calls[0];
    const parsed = new URL(String(url));
    expect(parsed.origin).toBe("http://backend.test");
    expect(parsed.pathname).toBe("/v1/currents");
    expect(parsed.searchParams.get("since")).toBe("2026-04-29T00:00:00.000Z");
    expect(parsed.searchParams.get("until")).toBe("2026-04-30T00:00:00.000Z");
    expect(parsed.searchParams.get("topic")).toBe("ai");
    expect(parsed.searchParams.get("stance")).toBe("support");
    expect(parsed.searchParams.get("limit")).toBe("7");
    expect(init).toMatchObject({ method: "GET", cache: "no-store" });
  });

  it("the follow-up route strips cookie and authorization before forwarding", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("event: done\ndata: {}\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream; charset=utf-8" },
      }),
    );

    const { POST } = await import("@/app/api/currents/[id]/follow-up/route");
    const req = new Request("http://localhost:3000/api/currents/opinion-1/follow-up", {
      method: "POST",
      headers: {
        authorization: "Bearer secret",
        cookie: "session=secret",
        "content-type": "application/json",
        "user-agent": "vitest-agent",
        "x-client-fingerprint": "client-supplied",
        "x-fingerprint": "internal",
        "x-forwarded-for": "203.0.113.7, 10.0.0.2",
      },
      body: JSON.stringify({ question: "What follows?" }),
    });

    await POST(req as never, { params: Promise.resolve({ id: "opinion-1" }) });

    const [url, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init.headers);
    expect(String(url)).toBe("http://backend.test/v1/currents/opinion-1/follow-up");
    expect(headers.get("cookie")).toBeNull();
    expect(headers.get("authorization")).toBeNull();
    expect(headers.get("x-client-fingerprint")).toBeNull();
    expect(headers.get("x-fingerprint")).toBeNull();
    expect(headers.get("user-agent")).toBe("vitest-agent");
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("x-forwarded-for")).toBe("203.0.113.7");
    expect(headers.get("x-client-id")).toMatch(/^[a-f0-9]{32}$/);
  });

  it("fingerprintFor is deterministic for the same IP, user-agent, and UTC day", async () => {
    const { fingerprintFor } = await import("@/lib/currentsFingerprint");
    const req = new Request("http://localhost:3000/api/currents/opinion-1/follow-up", {
      headers: {
        "user-agent": "vitest-agent",
        "x-forwarded-for": "203.0.113.7",
      },
    });
    const sameDayA = fingerprintFor(req, new Date("2026-04-29T00:00:00.000Z"));
    const sameDayB = fingerprintFor(req, new Date("2026-04-29T23:59:59.000Z"));
    const nextDay = fingerprintFor(req, new Date("2026-04-30T00:00:00.000Z"));

    expect(sameDayA).toBe(sameDayB);
    expect(sameDayA).toMatch(/^[a-f0-9]{32}$/);
    expect(nextDay).not.toBe(sameDayA);
  });

  it("SSE pass-through preserves the text/event-stream content type", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("event: heartbeat\ndata: {}\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream; charset=utf-8" },
      }),
    );

    const { GET } = await import("@/app/api/currents/stream/route");
    const res = await GET(new Request("http://localhost:3000/api/currents/stream") as never);

    expect(res.headers.get("content-type")).toBe("text/event-stream; charset=utf-8");
    expect(res.headers.get("cache-control")).toBe("no-cache, no-transform");
  });
});
