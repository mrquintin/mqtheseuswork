import { beforeEach, describe, expect, it, vi } from "vitest";

const dbMock = vi.hoisted(() => ({
  conclusion: {
    findFirst: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    deleteMany: vi.fn(),
  },
  dashboardDismissal: {
    upsert: vi.fn(),
    deleteMany: vi.fn(),
  },
}));

const tenantMock = vi.hoisted(() => ({
  requireTenantContext: vi.fn(),
}));

const cacheMock = vi.hoisted(() => ({
  revalidatePath: vi.fn(),
}));

vi.mock("@/lib/db", () => ({
  db: dbMock,
}));

vi.mock("@/lib/tenant", () => tenantMock);

vi.mock("next/cache", () => cacheMock);

import {
  dismissConclusionFromMyDashboard,
  showAllDashboardConclusionsAgain,
  undoConclusionDismissalFromMyDashboard,
} from "@/app/(authed)/dashboard/actions";

describe("dashboard dismissal server actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    tenantMock.requireTenantContext.mockResolvedValue({
      organizationId: "org-1",
      organizationSlug: "theseus-local",
      founderId: "founder-1",
      founderName: "alpha",
      founderUsername: "alpha",
      role: "admin",
    });
    dbMock.conclusion.findFirst.mockResolvedValue({ id: "conclusion-1" });
    dbMock.dashboardDismissal.upsert.mockResolvedValue({ id: "dismissal-1" });
    dbMock.dashboardDismissal.deleteMany.mockResolvedValue({ count: 1 });
  });

  it("writes a DashboardDismissal row and never mutates Conclusion", async () => {
    const formData = new FormData();
    formData.set("conclusionId", "conclusion-1");

    const result = await dismissConclusionFromMyDashboard(formData);

    expect(result).toEqual({ ok: true, conclusionId: "conclusion-1" });
    expect(dbMock.conclusion.findFirst).toHaveBeenCalledWith({
      where: { id: "conclusion-1", organizationId: "org-1" },
      select: { id: true },
    });
    expect(dbMock.dashboardDismissal.upsert).toHaveBeenCalledWith({
      where: {
        founderId_conclusionId: {
          founderId: "founder-1",
          conclusionId: "conclusion-1",
        },
      },
      update: {},
      create: {
        founderId: "founder-1",
        conclusionId: "conclusion-1",
      },
    });
    expect(dbMock.conclusion.update).not.toHaveBeenCalled();
    expect(dbMock.conclusion.delete).not.toHaveBeenCalled();
    expect(dbMock.conclusion.deleteMany).not.toHaveBeenCalled();
    expect(cacheMock.revalidatePath).toHaveBeenCalledWith("/dashboard");
  });

  it("undo deletes only the caller's org-scoped DashboardDismissal row", async () => {
    const result = await undoConclusionDismissalFromMyDashboard("conclusion-1");

    expect(result).toEqual({ ok: true, conclusionId: "conclusion-1" });
    expect(dbMock.dashboardDismissal.deleteMany).toHaveBeenCalledWith({
      where: {
        founderId: "founder-1",
        conclusionId: "conclusion-1",
        conclusion: { organizationId: "org-1" },
      },
    });
    expect(cacheMock.revalidatePath).toHaveBeenCalledWith("/dashboard");
  });

  it("show all again clears every org-scoped DashboardDismissal for the caller", async () => {
    const result = await showAllDashboardConclusionsAgain();

    expect(result).toEqual({ ok: true, count: 1 });
    expect(dbMock.dashboardDismissal.deleteMany).toHaveBeenCalledWith({
      where: {
        founderId: "founder-1",
        conclusion: { organizationId: "org-1" },
      },
    });
    expect(cacheMock.revalidatePath).toHaveBeenCalledWith("/dashboard");
  });
});
