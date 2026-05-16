import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

const dbMock = vi.hoisted(() => ({
  publishedConclusion: {
    findFirst: vi.fn(),
  },
  publicResponse: {
    count: vi.fn(),
    create: vi.fn(),
  },
}));

const emailMock = vi.hoisted(() => ({
  notifyFounderOfResponse: vi.fn(),
}));

const triageMock = vi.hoisted(() => ({
  seedTriageRow: vi.fn(),
}));

vi.mock("@/lib/db", () => ({
  db: dbMock,
}));

vi.mock("@/lib/responsesEmail", () => emailMock);

vi.mock("@/lib/responseTriageApi", () => triageMock);

import { POST } from "@/app/api/public/responses/route";

const publishedConclusion = {
  id: "pub-1",
  organizationId: "org-1",
  slug: "falsifiable-inference",
  version: 1,
  payloadJson: JSON.stringify({ conclusionText: "Inference should stay falsifiable" }),
};

const persistedResponse = {
  id: "resp-1",
  organizationId: "org-1",
  publishedConclusionId: "pub-1",
  kind: "counter_argument",
  body: "This is a sufficiently detailed counter argument from a reader.",
  citationUrl: "https://example.com/source",
  submitterEmail: "reader@example.com",
  orcid: "",
  pseudonymous: false,
  status: "pending",
  moderatorNote: "",
  createdAt: new Date("2026-05-08T12:00:00.000Z"),
  seenAt: null,
};

function jsonRequest(body: Record<string, unknown>) {
  return new Request("http://localhost:3000/api/public/responses", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: "https://theseuscodex.com",
    },
    body: JSON.stringify(body),
  }) as unknown as NextRequest;
}

function validBody() {
  return {
    publishedConclusionId: "pub-1",
    kind: "counter_argument",
    body: "This is a sufficiently detailed counter argument from a reader.",
    citationUrl: "https://example.com/source",
    submitterEmail: "reader@example.com",
    orcid: "",
    pseudonymous: false,
  };
}

describe("POST /api/public/responses founder email notification", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    dbMock.publishedConclusion.findFirst.mockResolvedValue(publishedConclusion);
    dbMock.publicResponse.count.mockResolvedValue(0);
    dbMock.publicResponse.create.mockResolvedValue(persistedResponse);
    triageMock.seedTriageRow.mockResolvedValue(undefined);
    emailMock.notifyFounderOfResponse.mockResolvedValue({
      delivered: true,
      provider: "resend",
    });
  });

  it("returns 200 when the email send fails", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    emailMock.notifyFounderOfResponse.mockRejectedValue(new Error("mail down"));

    const res = await POST(jsonRequest(validBody()));
    const body = await res.json();
    await Promise.resolve();

    expect(res.status).toBe(200);
    expect(body).toEqual({ ok: true, id: "resp-1" });
    expect(errorSpy).toHaveBeenCalledWith(
      "[public responses] founder notification failed:",
      expect.any(Error),
    );
    errorSpy.mockRestore();
  });

  it("still persists the row when the email send fails", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    emailMock.notifyFounderOfResponse.mockRejectedValue(new Error("mail down"));

    const res = await POST(jsonRequest(validBody()));
    await Promise.resolve();

    expect(res.status).toBe(200);
    expect(dbMock.publicResponse.create).toHaveBeenCalledWith({
      data: {
        organizationId: "org-1",
        publishedConclusionId: "pub-1",
        kind: "counter_argument",
        body: "This is a sufficiently detailed counter argument from a reader.",
        citationUrl: "https://example.com/source",
        submitterEmail: "reader@example.com",
        orcid: "",
        pseudonymous: false,
        publishConsent: false,
        status: "pending",
      },
    });
    errorSpy.mockRestore();
  });

  it("does not block the browser response on a slow mail provider", async () => {
    emailMock.notifyFounderOfResponse.mockReturnValue(new Promise(() => undefined));

    const started = Date.now();
    const res = await POST(jsonRequest(validBody()));
    const elapsedMs = Date.now() - started;

    expect(res.status).toBe(200);
    expect(elapsedMs).toBeLessThan(1500);
    expect(emailMock.notifyFounderOfResponse).toHaveBeenCalledWith(
      persistedResponse,
      publishedConclusion,
    );
  });
});
