"use server";

import { revalidatePath } from "next/cache";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";
import { canWrite } from "@/lib/roles";

const KNOWN_PROVENANCE = new Set([
  "PROPRIETARY",
  "ENDORSED_EXTERNAL",
  "STUDIED_EXTERNAL",
  "OPPOSING_EXTERNAL",
] as const);

type ProvenanceKindStr =
  | "PROPRIETARY"
  | "ENDORSED_EXTERNAL"
  | "STUDIED_EXTERNAL"
  | "OPPOSING_EXTERNAL";

/**
 * Server action for the triage page (prompt 09).
 *
 * Re-tags one upload's provenance. Authorization mirrors every other
 * upload-mutation surface: the founder must be in the org and have a
 * write-capable role. External provenance kinds require a ≥30-char
 * rationale; PROPRIETARY clears any prior rationale.
 *
 * Note: noosphere-side artifact rows are kept in lockstep by the
 * codex bridge on the next sync — same pattern as `visibility` edits.
 * This action only touches the Codex side.
 */
export async function retagAction(formData: FormData): Promise<void> {
  const tenant = await requireTenantContext();
  if (!tenant) throw new Error("unauthenticated");
  if (!canWrite(tenant.role)) throw new Error("forbidden");

  const uploadId = String(formData.get("uploadId") ?? "").trim();
  const rawProvenance = String(formData.get("provenance") ?? "")
    .trim()
    .toUpperCase();
  const rationale = String(formData.get("rationale") ?? "").trim();

  if (!uploadId) throw new Error("missing uploadId");
  if (!KNOWN_PROVENANCE.has(rawProvenance as ProvenanceKindStr)) {
    throw new Error(`unknown provenance kind: ${rawProvenance}`);
  }
  const provenance = rawProvenance as ProvenanceKindStr;
  const isExternal = provenance !== "PROPRIETARY";
  if (isExternal && rationale.length < 30) {
    throw new Error(
      "External provenance requires a rationale of at least 30 characters.",
    );
  }

  await db.upload.update({
    where: {
      id: uploadId,
      organizationId: tenant.organizationId,
    },
    data: {
      provenance,
      provenanceRationale: isExternal ? rationale : null,
    },
  });

  revalidatePath("/library/triage");
  revalidatePath("/library");
}
