import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextResponse } from "next/server";

vi.mock("@/lib/auth", () => ({
  getFounder: vi.fn(),
}));

vi.mock("@/lib/db", () => ({
  db: {
    $queryRaw: vi.fn().mockResolvedValue([]),
    $executeRaw: vi.fn().mockResolvedValue(0),
  },
}));

vi.mock("child_process", () => ({
  spawn: vi.fn().mockImplementation(() => {
    const EventEmitter = require("events");
    const proc = new EventEmitter();
    proc.stdout = new EventEmitter();
    proc.stderr = new EventEmitter();
    setTimeout(() => {
      proc.stdout.emit("data", Buffer.from('{"ledger_entry_id":"test-ledger-1"}'));
      proc.emit("close", 0);
    }, 0);
    return proc;
  }),
}));

import { getFounder } from "@/lib/auth";
import { withGated, submitToRigorGate } from "@/lib/api/round3";

const mockGetFounder = vi.mocked(getFounder);

describe("withGated enforces rigor gate on all mutations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("rejects unauthenticated requests with 401", async () => {
    mockGetFounder.mockResolvedValue(null);

    const handler = withGated("test.action", async () => {
      return NextResponse.json({ ok: true });
    });

    const req = new Request("http://localhost:3000/api/test", {
      method: "POST",
    });
    const res = await handler(req);
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body.error).toBe("Unauthorized");
  });

  it("passes authenticated gated requests through to handler", async () => {
    mockGetFounder.mockResolvedValue({
      id: "founder-1",
      name: "Test Founder",
      username: "testfounder",
      organizationId: "org-1",
      organization: { slug: "test-org" },
    } as Awaited<ReturnType<typeof getFounder>>);

    const handler = withGated("test.action", async () => {
      return NextResponse.json({ ok: true, data: { result: "success" } });
    });

    const req = new Request("http://localhost:3000/api/test", {
      method: "POST",
    });
    const res = await handler(req);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.ledgerEntryId).toBeDefined();
    expect(body.ledgerEntryId).toBeTruthy();
  });

  it("includes ledger entry ID in every gated response", async () => {
    mockGetFounder.mockResolvedValue({
      id: "founder-1",
      name: "Test Founder",
      username: "testfounder",
      organizationId: "org-1",
      organization: { slug: "test-org" },
    } as Awaited<ReturnType<typeof getFounder>>);

    const handler = withGated("promotion", async () => {
      return NextResponse.json({ ok: true });
    });

    const req = new Request("http://localhost:3000/api/test", {
      method: "POST",
    });
    const res = await handler(req);
    const body = await res.json();
    expect(body.ledgerEntryId).toMatch(/^(test-ledger|gate-|dev-gate-)/);
  });

  it("all round3 API routes use withGated", async () => {
    const routePaths = [
      "@/app/api/round3/inverse/run/route",
      "@/app/api/round3/review/run/route",
      "@/app/api/round3/decay/revalidate/route",
      "@/app/api/round3/gate/submit/route",
      "@/app/api/round3/gate/[id]/override/route",
      "@/app/api/round3/methods/package/route",
      "@/app/api/round3/methods/document/route",
      "@/app/api/round3/interop/build/route",
    ];

    for (const routePath of routePaths) {
      const route = await import(routePath);
      expect(route.POST).toBeDefined();
      expect(typeof route.POST).toBe("function");

      mockGetFounder.mockResolvedValue(null);
      const req = new Request("http://localhost:3000/api/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const res = await route.POST(req, { params: Promise.resolve({ id: "test-id" }) });
      expect(res.status).toBe(401);
      const body = await res.json();
      expect(body.error).toBe("Unauthorized");
    }
  });

  it("submitToRigorGate returns approved with ledger entry", async () => {
    const result = await submitToRigorGate("test.kind", "TestFounder");
    expect(result.approved).toBe(true);
    expect(result.ledgerEntryId).toBeTruthy();
  });
});
