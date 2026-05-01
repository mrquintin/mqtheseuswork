"use server";

import { revalidatePath } from "next/cache";

import { db } from "@/lib/db";
import { canReadContactInbox } from "@/lib/roles";
import { sanitizeAndCap } from "@/lib/sanitizeText";
import { requireTenantContext } from "@/lib/tenant";

const CONTACT_INBOX_PATH = "/admin/contact";
const MAX_NOTE_LENGTH = 2000;

export async function toggleContactTriaged(formData: FormData) {
  const tenant = await requireContactInboxAdmin();
  const id = formText(formData.get("id"));
  if (!id) throw new Error("Contact submission id is required.");

  const triaged = formText(formData.get("triaged")) === "true";
  await db.contactSubmission.update({
    where: { id },
    data: {
      triagedAt: triaged ? new Date() : null,
      triagedBy: triaged ? tenant.founderId : null,
    },
  });

  revalidatePath(CONTACT_INBOX_PATH);
}

export async function updateContactNotes(formData: FormData) {
  await requireContactInboxAdmin();
  const id = formText(formData.get("id"));
  if (!id) throw new Error("Contact submission id is required.");

  const notes = sanitizeAndCap(
    formText(formData.get("notes")),
    MAX_NOTE_LENGTH,
  ).trim();
  await db.contactSubmission.update({
    where: { id },
    data: { notes: notes || null },
  });

  revalidatePath(CONTACT_INBOX_PATH);
}

async function requireContactInboxAdmin() {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("Not authenticated.");
  if (!canReadContactInbox(tenant.role)) {
    throw new Error("Only admins can read the contact inbox.");
  }
  return tenant;
}

function formText(value: FormDataEntryValue | null): string {
  return typeof value === "string" ? value : "";
}
