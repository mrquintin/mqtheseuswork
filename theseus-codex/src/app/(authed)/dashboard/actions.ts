"use server";

import { revalidatePath } from "next/cache";
import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

function readConclusionId(input: FormData | string): string {
  if (typeof input === "string") return input.trim();
  return String(input.get("conclusionId") || "").trim();
}

type DashboardActionResult =
  | { ok: true; conclusionId?: string; count?: number }
  | { ok: false; error: string; count?: number };

/**
 * Hide a conclusion from the calling founder's dashboard only.
 *
 * This writes to `DashboardDismissal`, a per-founder/per-conclusion join
 * table. It is hide-only, reversible, and has no effect on the underlying
 * `Conclusion` row or on any other founder's dashboard. It is deliberately
 * distinct from `ConclusionDeletionRequest`, which is org-wide and must go
 * through peer review before the conclusion itself can be deleted.
 */
export async function dismissConclusionFromMyDashboard(
  input: FormData | string,
): Promise<DashboardActionResult> {
  const conclusionId = readConclusionId(input);
  if (!conclusionId) {
    return { ok: false, error: "conclusionId required" };
  }

  const tenant = await requireTenantContext();
  if (!tenant) {
    return { ok: false, error: "Unauthorized" };
  }

  const conclusion = await db.conclusion.findFirst({
    where: { id: conclusionId, organizationId: tenant.organizationId },
    select: { id: true },
  });
  if (!conclusion) {
    return { ok: false, error: "Conclusion not found" };
  }

  await db.dashboardDismissal.upsert({
    where: {
      founderId_conclusionId: {
        founderId: tenant.founderId,
        conclusionId,
      },
    },
    update: {},
    create: {
      founderId: tenant.founderId,
      conclusionId,
    },
  });
  revalidatePath("/dashboard");
  return { ok: true, conclusionId };
}

export async function undoConclusionDismissalFromMyDashboard(
  input: FormData | string,
): Promise<DashboardActionResult> {
  const conclusionId = readConclusionId(input);
  if (!conclusionId) {
    return { ok: false, error: "conclusionId required" };
  }

  const tenant = await requireTenantContext();
  if (!tenant) {
    return { ok: false, error: "Unauthorized" };
  }

  await db.dashboardDismissal.deleteMany({
    where: {
      founderId: tenant.founderId,
      conclusionId,
      conclusion: { organizationId: tenant.organizationId },
    },
  });
  revalidatePath("/dashboard");
  return { ok: true, conclusionId };
}

export async function showAllDashboardConclusionsAgain(): Promise<DashboardActionResult> {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return { ok: false, error: "Unauthorized", count: 0 };
  }

  const result = await db.dashboardDismissal.deleteMany({
    where: {
      founderId: tenant.founderId,
      conclusion: { organizationId: tenant.organizationId },
    },
  });
  revalidatePath("/dashboard");
  return { ok: true, count: result.count };
}
