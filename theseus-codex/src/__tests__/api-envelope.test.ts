/**
 * Regression tests for the unified API envelope contract.
 * See `docs/architecture/API_Envelope_Contract.md`.
 *
 * Three concerns:
 *   1. `withApiHandler` shapes success and error responses correctly,
 *      including correlation ids, custom headers, and the legacy alias.
 *   2. `parseEnvelope` unwraps both envelope and legacy bodies, and
 *      raises typed `EnvelopeError` instances on failures.
 *   3. Public route handlers (methodology + calibration manifests)
 *      emit `meta.schemaVersion` and accept the legacy alias.
 */

import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/envelope";
import { withApiHandler } from "@/lib/api/handler";
import { EnvelopeError, parseEnvelope } from "@/lib/api/parseEnvelope";

function makeReq(url = "http://localhost/api/test", init: RequestInit = {}) {
  // The Next.js handler signature accepts `NextRequest` but `withApiHandler`
  // only touches the `Request`-compatible surface: `.url`, `.headers.get`,
  // `.json()`. Casting keeps the test stable across Next versions.
  return new Request(url, init) as unknown as Parameters<
    ReturnType<typeof withApiHandler<unknown>>
  >[0];
}

describe("envelope success path", () => {
  it("wraps data in { ok, data, meta } and stamps a correlation id", async () => {
    const handler = withApiHandler<{ greeting: string }>(async () => ({
      data: { greeting: "hi" },
      meta: { schemaVersion: 1 },
    }));

    const res = await handler(makeReq());
    expect(res.status).toBe(200);
    expect(res.headers.get("x-correlation-id")).toMatch(/[0-9a-f-]{8,}/);
    const body = await res.json();
    expect(body).toEqual({
      ok: true,
      data: { greeting: "hi" },
      meta: { schemaVersion: 1 },
    });
  });

  it("omits meta when the handler omits it", async () => {
    const handler = withApiHandler<string>(async () => ({ data: "raw" }));
    const res = await handler(makeReq());
    const body = (await res.json()) as { ok: boolean; data: string; meta?: unknown };
    expect(body.ok).toBe(true);
    expect(body.data).toBe("raw");
    expect("meta" in body).toBe(false);
  });

  it("passes through extra response headers from the handler", async () => {
    const handler = withApiHandler(async () => ({
      data: { ok: true },
      headers: { "Cache-Control": "public, max-age=60" },
    }));
    const res = await handler(makeReq());
    expect(res.headers.get("cache-control")).toBe("public, max-age=60");
  });
});

describe("envelope failure path", () => {
  it("converts ApiError into { ok:false, error } with the right status", async () => {
    const handler = withApiHandler(async () => {
      throw new ApiError("validation_error", "missing field", { details: { field: "name" } });
    });
    const res = await handler(makeReq());
    expect(res.status).toBe(400);
    const body = (await res.json()) as {
      ok: false;
      error: { code: string; message: string; correlationId: string; details: unknown };
    };
    expect(body.ok).toBe(false);
    expect(body.error.code).toBe("validation_error");
    expect(body.error.message).toBe("missing field");
    expect(body.error.details).toEqual({ field: "name" });
    expect(body.error.correlationId).toEqual(res.headers.get("x-correlation-id"));
  });

  it("rate_limited responses carry the Retry-After header", async () => {
    const handler = withApiHandler(async () => {
      throw new ApiError("rate_limited", "slow down", { headers: { "Retry-After": "30" } });
    });
    const res = await handler(makeReq());
    expect(res.status).toBe(429);
    expect(res.headers.get("retry-after")).toBe("30");
  });

  it("surfaces unexpected throws as internal_error without leaking the cause", async () => {
    const consoleErr = vi.spyOn(console, "error").mockImplementation(() => {});
    const handler = withApiHandler(async () => {
      throw new Error("kaboom: secret-detail");
    });
    const res = await handler(makeReq());
    expect(res.status).toBe(500);
    const body = (await res.json()) as { error: { code: string; message: string } };
    expect(body.error.code).toBe("internal_error");
    expect(body.error.message).toBe("Internal server error");
    consoleErr.mockRestore();
  });
});

describe("legacy alias", () => {
  it("returns the raw legacy body when the header opt-in is set", async () => {
    const handler = withApiHandler(async () => ({
      data: { wrapped: true },
      legacy: { wrapped: true, legacyOnlyField: "yes" },
    }));
    const res = await handler(
      makeReq("http://localhost/api/test", {
        headers: { "x-theseus-envelope": "legacy" },
      }),
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("deprecation")).toBe("true");
    const body = await res.json();
    expect(body).toEqual({ wrapped: true, legacyOnlyField: "yes" });
  });

  it("honors the ?envelope=legacy query param too", async () => {
    const handler = withApiHandler(async () => ({
      data: { wrapped: true },
      legacy: { legacy: true },
    }));
    const res = await handler(makeReq("http://localhost/api/test?envelope=legacy"));
    const body = await res.json();
    expect(body).toEqual({ legacy: true });
    expect(res.headers.get("deprecation")).toBe("true");
  });

  it("falls back to `data` when the handler omits a legacy body", async () => {
    const handler = withApiHandler(async () => ({ data: { a: 1 } }));
    const res = await handler(
      makeReq("http://localhost/api/test", {
        headers: { "x-theseus-envelope": "legacy" },
      }),
    );
    expect(await res.json()).toEqual({ a: 1 });
  });

  it("legacy alias still serves errors in legacy { error } shape", async () => {
    const handler = withApiHandler(async () => {
      throw new ApiError("not_found", "nope");
    });
    const res = await handler(
      makeReq("http://localhost/api/test", {
        headers: { "x-theseus-envelope": "legacy" },
      }),
    );
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: "nope" });
  });
});

describe("parseEnvelope", () => {
  function jsonResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }

  it("unwraps a successful envelope and returns data + meta", async () => {
    const env = await parseEnvelope<{ x: number }>(
      jsonResponse({ ok: true, data: { x: 7 }, meta: { schemaVersion: 1 } }),
    );
    expect(env.data).toEqual({ x: 7 });
    expect(env.meta).toEqual({ schemaVersion: 1 });
  });

  it("throws EnvelopeError with typed code on failure", async () => {
    const failing = jsonResponse(
      {
        ok: false,
        error: {
          code: "validation_error",
          message: "bad input",
          correlationId: "abc-123",
        },
      },
      400,
    );
    await expect(parseEnvelope(failing)).rejects.toMatchObject({
      code: "validation_error",
      correlationId: "abc-123",
      status: 400,
    });
  });

  it("accepts un-enveloped 2xx bodies in non-strict mode (legacy bridge)", async () => {
    const env = await parseEnvelope<{ raw: true }>(jsonResponse({ raw: true }));
    expect(env.data).toEqual({ raw: true });
  });

  it("refuses un-enveloped bodies in strict mode", async () => {
    await expect(
      parseEnvelope(jsonResponse({ raw: true }), { strict: true }),
    ).rejects.toBeInstanceOf(EnvelopeError);
  });
});

describe("public manifest routes carry meta.schemaVersion", () => {
  it("methodology manifest GET advertises schemaVersion=1", async () => {
    vi.resetModules();
    vi.doMock("@/lib/methodologyManifest", () => ({
      MANIFEST_SCHEMA_VERSION: 1,
      buildMethodologyManifest: vi.fn().mockResolvedValue({
        v: 1,
        schema: "theseus.methodology.manifest",
        generatedAt: "2026-05-13T00:00:00.000Z",
        methods: [],
        edges: [],
        publicFailureModes: [],
        publicTrackRecords: [],
      }),
    }));
    const { GET } = await import("@/app/api/public/methodology/manifest/route");
    const res = await GET(makeReq("http://localhost/api/public/methodology/manifest"));
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      ok: boolean;
      data: { v: number };
      meta: { schemaVersion: number };
    };
    expect(body.ok).toBe(true);
    expect(body.data.v).toBe(1);
    expect(body.meta.schemaVersion).toBe(1);
    vi.doUnmock("@/lib/methodologyManifest");
  });

  it("methodology manifest legacy alias returns the raw manifest", async () => {
    vi.resetModules();
    vi.doMock("@/lib/methodologyManifest", () => ({
      MANIFEST_SCHEMA_VERSION: 1,
      buildMethodologyManifest: vi.fn().mockResolvedValue({
        v: 1,
        schema: "theseus.methodology.manifest",
        generatedAt: "2026-05-13T00:00:00.000Z",
        methods: [],
        edges: [],
        publicFailureModes: [],
        publicTrackRecords: [],
      }),
    }));
    const { GET } = await import("@/app/api/public/methodology/manifest/route");
    const res = await GET(
      makeReq("http://localhost/api/public/methodology/manifest?envelope=legacy"),
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("deprecation")).toBe("true");
    const body = (await res.json()) as { v: number; ok?: unknown };
    expect(body.v).toBe(1);
    expect("ok" in body).toBe(false);
    vi.doUnmock("@/lib/methodologyManifest");
  });
});
