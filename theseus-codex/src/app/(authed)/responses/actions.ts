"use server";

import { revalidatePath } from "next/cache";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

const RESPONSES_INBOX_PATH = "/responses";

export async function markPublicResponseSeen(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");

  const id = formText(formData.get("id"));
  if (!id) throw new Error("Public response id is required.");

  const isSeen = formText(formData.get("seen")) === "true";
  await db.publicResponse.updateMany({
    where: {
      id,
      organizationId: tenant.organizationId,
    },
    data: {
      seenAt: isSeen ? null : new Date(),
    },
  });

  revalidatePath(RESPONSES_INBOX_PATH);
}

function formText(value: FormDataEntryValue | null): string {
  return typeof value === "string" ? value : "";
}
