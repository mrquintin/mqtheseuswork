import { beforeEach, describe, expect, it, vi } from "vitest";

const dbMock = vi.hoisted(() => ({
  contactSubmission: {
    count: vi.fn(),
    create: vi.fn(),
  },
}));

vi.mock("@/lib/db", () => ({
  db: dbMock,
}));

import { POST } from "@/app/api/contact/route";

function jsonRequest(body: unknown, headers: Record<string, string> = {}) {
  return new Request("http://localhost:3000/api/contact", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "User-Agent": "vitest",
      "X-Forwarded-For": "203.0.113.10",
      ...headers,
    },
    body: JSON.stringify(body),
  });
}

describe("POST /api/contact", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    dbMock.contactSubmission.count.mockResolvedValue(0);
    dbMock.contactSubmission.create.mockResolvedValue({ id: "contact-1" });
  });

  it("rejects missing required fields with 400", async () => {
    const res = await POST(jsonRequest({}));
    const body = await res.json();

    expect(res.status).toBe(400);
    expect(body.fieldErrors).toMatchObject({
      fromName: "Name is required.",
      fromEmail: "Email is required.",
      body: "Message must be at least 10 characters.",
    });
    expect(dbMock.contactSubmission.count).not.toHaveBeenCalled();
    expect(dbMock.contactSubmission.create).not.toHaveBeenCalled();
  });

  it("returns 200 and writes nothing when the honeypot is filled", async () => {
    const res = await POST(
      jsonRequest({
        company_url: "https://spam.example",
        fromName: "",
        fromEmail: "",
        body: "",
      }),
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual({ ok: true });
    expect(dbMock.contactSubmission.count).not.toHaveBeenCalled();
    expect(dbMock.contactSubmission.create).not.toHaveBeenCalled();
  });

  it("rejects an over-length body with 400", async () => {
    const res = await POST(
      jsonRequest({
        fromName: "Prospective Speaker",
        fromEmail: "speaker@example.com",
        body: "a".repeat(4001),
      }),
    );
    const body = await res.json();

    expect(res.status).toBe(400);
    expect(body.fieldErrors).toMatchObject({
      body: "Message must be 4000 characters or fewer.",
    });
    expect(dbMock.contactSubmission.create).not.toHaveBeenCalled();
  });

  it("writes a valid submission and strips HTML from the stored body", async () => {
    const res = await POST(
      jsonRequest({
        fromName: "Prospective Guest",
        fromEmail: "Guest@Example.com",
        subject: "Summit speaker",
        body: "Hello <b>Theseus</b>, I can speak about prediction markets.",
      }),
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual({ ok: true, id: "contact-1" });
    expect(dbMock.contactSubmission.count).toHaveBeenCalledWith({
      where: {
        ipHash: expect.stringMatching(/^[a-f0-9]{64}$/),
        createdAt: { gte: expect.any(Date) },
      },
    });
    expect(dbMock.contactSubmission.create).toHaveBeenCalledWith({
      data: {
        fromName: "Prospective Guest",
        fromEmail: "guest@example.com",
        subject: "Summit speaker",
        body: "Hello Theseus, I can speak about prediction markets.",
        organizationId: null,
        ipHash: expect.stringMatching(/^[a-f0-9]{64}$/),
        userAgent: "vitest",
      },
      select: { id: true },
    });
  });

  it("rejects after five submissions per hashed network within 24 hours", async () => {
    dbMock.contactSubmission.count.mockResolvedValue(5);

    const res = await POST(
      jsonRequest({
        fromName: "Reader",
        fromEmail: "reader@example.com",
        body: "This is a legitimate message that exceeds ten characters.",
      }),
    );
    const body = await res.json();

    expect(res.status).toBe(429);
    expect(body.error).toMatch(/Too many contact submissions/);
    expect(dbMock.contactSubmission.create).not.toHaveBeenCalled();
  });
});
