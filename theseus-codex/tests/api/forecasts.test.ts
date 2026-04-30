import { createHash, createHmac } from "crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.fn();
const founderMock = vi.fn();

function request(url: string, init?: RequestInit): Request {
  return new Request(url, init);
}

async function readChunks(res: Response): Promise<string[]> {
  const reader = res.body?.getReader();
  if (!reader) return [];
  const decoder = new TextDecoder();
  const chunks: string[] = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(decoder.decode(value, { stream: true }));
  }
  const tail = decoder.decode();
  if (tail) chunks.push(tail);
  return chunks;
}

function delayedStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const chunk of chunks) {
        await new Promise((resolve) => setTimeout(resolve, 50));
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

describe("forecasts public API proxy routes", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("FORECASTS_API_URL", "http://backend.test");
    vi.stubEnv("FORECASTS_OPERATOR_SECRET", "secret");
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
    founderMock.mockReset();
    vi.doMock("@/lib/auth", () => ({ getFounder: founderMock }));
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.doUnmock("@/lib/auth");
  });

  const publicJsonRoutes = [
    {
      name: "list forecasts",
      importPath: "@/app/api/forecasts/route",
      method: "GET",
      url: "http://localhost:3000/api/forecasts?topic=macro&limit=3",
      upstreamPath: "/v1/forecasts",
      upstreamSearch: "?topic=macro&limit=3",
    },
    {
      name: "get forecast",
      importPath: "@/app/api/forecasts/[id]/route",
      method: "GET",
      url: "http://localhost:3000/api/forecasts/forecast-1",
      ctx: { params: Promise.resolve({ id: "forecast-1" }) },
      upstreamPath: "/v1/forecasts/forecast-1",
      upstreamSearch: "",
    },
    {
      name: "forecast sources",
      importPath: "@/app/api/forecasts/[id]/sources/route",
      method: "GET",
      url: "http://localhost:3000/api/forecasts/forecast-1/sources",
      ctx: { params: Promise.resolve({ id: "forecast-1" }) },
      upstreamPath: "/v1/forecasts/forecast-1/sources",
      upstreamSearch: "",
    },
    {
      name: "forecast resolution",
      importPath: "@/app/api/forecasts/[id]/resolution/route",
      method: "GET",
      url: "http://localhost:3000/api/forecasts/forecast-1/resolution",
      ctx: { params: Promise.resolve({ id: "forecast-1" }) },
      upstreamPath: "/v1/forecasts/forecast-1/resolution",
      upstreamSearch: "",
    },
    {
      name: "forecast bets",
      importPath: "@/app/api/forecasts/[id]/bets/route",
      method: "GET",
      url: "http://localhost:3000/api/forecasts/forecast-1/bets",
      ctx: { params: Promise.resolve({ id: "forecast-1" }) },
      upstreamPath: "/v1/forecasts/forecast-1/bets",
      upstreamSearch: "",
    },
    {
      name: "forecast follow-up",
      importPath: "@/app/api/forecasts/[id]/follow-up/route",
      method: "POST",
      url: "http://localhost:3000/api/forecasts/forecast-1/follow-up",
      ctx: { params: Promise.resolve({ id: "forecast-1" }) },
      requestInit: {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "user-agent": "vitest-agent",
          "x-forwarded-for": "203.0.113.4, 10.0.0.1",
        },
        body: JSON.stringify({ question: "What changed?" }),
      },
      upstreamPath: "/v1/forecasts/forecast-1/follow-up",
      upstreamSearch: "",
    },
    {
      name: "list markets",
      importPath: "@/app/api/forecasts/markets/route",
      method: "GET",
      url: "http://localhost:3000/api/forecasts/markets?source=KALSHI",
      upstreamPath: "/v1/markets",
      upstreamSearch: "?source=KALSHI",
    },
    {
      name: "get market",
      importPath: "@/app/api/forecasts/markets/[id]/route",
      method: "GET",
      url: "http://localhost:3000/api/forecasts/markets/market-1",
      ctx: { params: Promise.resolve({ id: "market-1" }) },
      upstreamPath: "/v1/markets/market-1",
      upstreamSearch: "",
    },
    {
      name: "portfolio summary",
      importPath: "@/app/api/portfolio/route",
      method: "GET",
      url: "http://localhost:3000/api/portfolio",
      upstreamPath: "/v1/portfolio",
      upstreamSearch: "",
    },
    {
      name: "portfolio calibration",
      importPath: "@/app/api/portfolio/calibration/route",
      method: "GET",
      url: "http://localhost:3000/api/portfolio/calibration",
      upstreamPath: "/v1/portfolio/calibration",
      upstreamSearch: "",
    },
    {
      name: "portfolio bets",
      importPath: "@/app/api/portfolio/bets/route",
      method: "GET",
      url: "http://localhost:3000/api/portfolio/bets?limit=5&offset=10",
      upstreamPath: "/v1/portfolio/bets",
      upstreamSearch: "?limit=5&offset=10",
    },
  ];

  for (const routeCase of publicJsonRoutes) {
    it(`${routeCase.name} returns upstream JSON unchanged`, async () => {
      const upstreamPayload = { route: routeCase.name, ok: true };
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(upstreamPayload), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

      const mod = await import(routeCase.importPath);
      const handler = mod[routeCase.method] as (req: Request, ctx?: unknown) => Promise<Response>;
      const res = await handler(request(routeCase.url, routeCase.requestInit), routeCase.ctx);

      const [url, init] = fetchMock.mock.calls[0];
      const parsed = new URL(String(url));
      expect(parsed.origin).toBe("http://backend.test");
      expect(parsed.pathname).toBe(routeCase.upstreamPath);
      expect(parsed.search).toBe(routeCase.upstreamSearch);
      expect(init).toMatchObject({ method: routeCase.method, cache: "no-store" });
      expect(res.status).toBe(200);
      expect(res.headers.get("content-type")).toBe("application/json");
      expect(await res.text()).toBe(JSON.stringify(upstreamPayload));
    });
  }

  it("public proxy refuses operator paths before fetch", async () => {
    const { proxyToForecasts } = await import("@/lib/forecastsApi");
    const res = await proxyToForecasts(request("http://localhost:3000/api/forecasts/operator"), "/v1/operator/live-bets");

    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("SSE pass-through forwards frames chunk-by-chunk in order", async () => {
    const frames = [
      "event: forecast.published\ndata: {\"n\":1}\n\n",
      "event: heartbeat\ndata: {\"n\":2}\n\n",
      "event: forecast.resolved\ndata: {\"n\":3}\n\n",
    ];
    fetchMock.mockResolvedValueOnce(
      new Response(delayedStream(frames), {
        status: 200,
        headers: { "content-type": "text/event-stream; charset=utf-8" },
      }),
    );

    const { GET } = await import("@/app/api/forecasts/stream/route");
    const res = await GET(request("http://localhost:3000/api/forecasts/stream") as never);

    expect(res.headers.get("content-type")).toBe("text/event-stream; charset=utf-8");
    expect(res.headers.get("cache-control")).toBe("no-cache, no-transform");
    expect(res.headers.get("connection")).toBe("keep-alive");
    expect(await readChunks(res)).toEqual(frames);
  });
});

describe("forecasts operator proxy routes", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("FORECASTS_API_URL", "http://backend.test");
    vi.stubEnv("FORECASTS_OPERATOR_SECRET", "secret");
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
    founderMock.mockReset();
    vi.doMock("@/lib/auth", () => ({ getFounder: founderMock }));
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.doUnmock("@/lib/auth");
  });

  const operatorRoutes = [
    {
      name: "authorize live",
      importPath: "@/app/(authed)/api/forecasts/operator/[id]/authorize-live/route",
      method: "POST",
      url: "http://localhost:3000/api/forecasts/operator/forecast-1/authorize-live",
      ctx: { params: Promise.resolve({ id: "forecast-1" }) },
      init: {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ operator_id: "founder-1", csrf_token: "csrf" }),
      },
    },
    {
      name: "confirm bet",
      importPath: "@/app/(authed)/api/forecasts/operator/[id]/bets/[betId]/confirm/route",
      method: "POST",
      url: "http://localhost:3000/api/forecasts/operator/forecast-1/bets/bet-1/confirm",
      ctx: { params: Promise.resolve({ id: "forecast-1", betId: "bet-1" }) },
      init: {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ operator_id: "founder-1", csrf_token: "csrf" }),
      },
    },
    {
      name: "engage kill switch",
      importPath: "@/app/(authed)/api/forecasts/operator/kill-switch/engage/route",
      method: "POST",
      url: "http://localhost:3000/api/forecasts/operator/kill-switch/engage",
      init: {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reason: "OPERATOR", csrf_token: "csrf" }),
      },
    },
    {
      name: "disengage kill switch",
      importPath: "@/app/(authed)/api/forecasts/operator/kill-switch/disengage/route",
      method: "POST",
      url: "http://localhost:3000/api/forecasts/operator/kill-switch/disengage",
      init: {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          operator_id: "founder-1",
          note: "Reviewed the incident and cleared live risk.",
          csrf_token: "csrf",
        }),
      },
    },
    {
      name: "live bets",
      importPath: "@/app/(authed)/api/forecasts/operator/live-bets/route",
      method: "GET",
      url: "http://localhost:3000/api/forecasts/operator/live-bets",
    },
    {
      name: "operator stream",
      importPath: "@/app/(authed)/api/forecasts/operator/stream/route",
      method: "GET",
      url: "http://localhost:3000/api/forecasts/operator/stream",
    },
  ];

  for (const routeCase of operatorRoutes) {
    it(`${routeCase.name} returns 401 without founder session`, async () => {
      founderMock.mockResolvedValueOnce(null);

      const mod = await import(routeCase.importPath);
      const handler = mod[routeCase.method] as (req: Request, ctx?: unknown) => Promise<Response>;
      const res = await handler(request(routeCase.url, routeCase.init), routeCase.ctx);

      expect(res.status).toBe(401);
      expect(fetchMock).not.toHaveBeenCalled();
    });
  }

  it("operator route signs the exact upstream path and body hash", async () => {
    const body = JSON.stringify({ operator_id: "founder-1", csrf_token: "csrf" });
    founderMock.mockResolvedValueOnce({
      id: "founder-1",
      name: "Founder",
      organization: { id: "org-1" },
      role: "founder",
    });
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "forecast-1" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const { POST } = await import("@/app/(authed)/api/forecasts/operator/[id]/authorize-live/route");
    const res = await POST(
      request("http://localhost:3000/api/forecasts/operator/forecast-1/authorize-live", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body,
      }) as never,
      { params: Promise.resolve({ id: "forecast-1" }) },
    );

    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    const parsed = new URL(String(url));
    const headers = new Headers(init.headers);
    const timestamp = headers.get("x-forecasts-timestamp");
    expect(parsed.pathname).toBe("/v1/operator/forecasts/forecast-1/authorize-live");
    expect(timestamp).toBeTruthy();
    const signedBody = JSON.stringify({
      operator_id: "founder-1",
      csrf_token: "founder:founder-1",
    });
    const bodyHash = createHash("sha256")
      .update(new TextEncoder().encode(signedBody))
      .digest("hex");
    const expected = createHmac("sha256", "secret")
      .update([timestamp, parsed.pathname, bodyHash].join("\n"), "utf8")
      .digest("hex");
    expect(headers.get("x-forecasts-operator")).toBe(expected);
  });
});
