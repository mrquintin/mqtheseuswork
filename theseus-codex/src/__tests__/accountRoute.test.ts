import { beforeEach, describe, expect, it, vi } from "vitest";

const authMock = vi.hoisted(() => ({
  getFounder: vi.fn(),
}));

const dbMock = vi.hoisted(() => ({
  founder: {
    update: vi.fn(),
  },
}));

vi.mock("@/lib/auth", () => authMock);

vi.mock("@/lib/db", () => ({
  db: dbMock,
}));

import { PATCH } from "@/app/api/account/route";

function request(body: unknown) {
  return new Request("http://localhost:3000/api/account", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("PATCH /api/account", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMock.getFounder.mockResolvedValue({
      id: "founder-1",
      organizationId: "org-1",
      name: "Seed Placeholder",
      username: "alpha",
      displayName: null,
      roleTitle: null,
      publicUrl: null,
    });
    dbMock.founder.update.mockImplementation(({ data }) => ({
      id: "founder-1",
      email: "founder@example.com",
      username: "alpha",
      name: "Seed Placeholder",
      displayName: data.displayName,
      roleTitle: data.roleTitle,
      publicUrl: data.publicUrl,
      bio: data.bio,
    }));
  });

  it.each([
    ["empty", ""],
    ["one-character", "A"],
    ["sixty-one-character", "A".repeat(61)],
  ])("rejects %s display names", async (_label, displayName) => {
    const res = await PATCH(request({ displayName, bio: "" }));

    expect(res.status).toBe(400);
    expect(dbMock.founder.update).not.toHaveBeenCalled();
  });

  it("rejects leading or trailing whitespace", async () => {
    const res = await PATCH(request({ displayName: " Ada", bio: "" }));

    expect(res.status).toBe(400);
    expect(dbMock.founder.update).not.toHaveBeenCalled();
  });

  it.each(["Al", "A".repeat(60)])("accepts valid 2-60 character display names", async (displayName) => {
    const res = await PATCH(
      request({
        displayName,
        roleTitle: "Research Partner",
        publicUrl: "https://example.com/profile",
        bio: "Short bio",
      }),
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.ok).toBe(true);
    expect(dbMock.founder.update).toHaveBeenCalledWith({
      where: { id: "founder-1" },
      data: {
        displayName,
        roleTitle: "Research Partner",
        publicUrl: "https://example.com/profile",
        bio: "Short bio",
      },
      select: {
        id: true,
        email: true,
        username: true,
        name: true,
        displayName: true,
        roleTitle: true,
        publicUrl: true,
        bio: true,
      },
    });
  });

  it("rejects invalid public links", async () => {
    const res = await PATCH(
      request({ displayName: "Ada", publicUrl: "javascript:alert(1)", bio: "" }),
    );

    expect(res.status).toBe(400);
    expect(dbMock.founder.update).not.toHaveBeenCalled();
  });
});
