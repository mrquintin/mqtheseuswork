import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import {
  acceptAlgorithm,
  listQueuedAlgorithms,
  mergeAlgorithm,
  rejectAlgorithm,
  type AlgorithmRow,
} from "@/lib/algorithmsApi";
import { requireTenantContext } from "@/lib/tenant";

import QueueClient from "./QueueClient";

export const dynamic = "force-dynamic";

/**
 * Founder triage queue for drafted LogicalAlgorithms.
 *
 * The noosphere AlgorithmDrafter (Round 19 prompt 02) lands rows here
 * as `DRAFT` / `UNDER_REVIEW`. The founder accepts, edits, rejects,
 * or merges; nothing on this page auto-promotes to `ACTIVE`.
 *
 * Each row carries:
 *
 *   - name, description, source principles (clickable to the principle
 *     detail page), inputs with observability sources, output shape,
 *     reasoning chain as numbered steps, trigger predicate, and the
 *     drafter's confidence note.
 *   - per-row actions: ACCEPT, ACCEPT-WITH-EDIT, REJECT (with reason),
 *     MERGE-WITH-EXISTING (selects another algorithm to merge into).
 *   - bulk-accept-with-individual-gate-check: the bulk button calls
 *     ACCEPT one row at a time so the gate fires per row instead of
 *     batched.
 *
 * Server actions are defined here and threaded to QueueClient.
 */
export default async function AlgorithmsQueuePage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const rows = await listQueuedAlgorithms(tenant.organizationId);

  async function acceptAction(formData: FormData) {
    "use server";
    const id = String(formData.get("id") ?? "").trim();
    if (!id) return;
    const tenant2 = await requireTenantContext();
    if (!tenant2) redirect("/login");
    const name = formData.get("name");
    const description = formData.get("description");
    const triggerPredicate = formData.get("triggerPredicate");
    await acceptAlgorithm(tenant2.organizationId, id, {
      name: typeof name === "string" && name.trim() ? name : undefined,
      description: typeof description === "string" ? description : undefined,
      triggerPredicate:
        typeof triggerPredicate === "string" && triggerPredicate.trim()
          ? triggerPredicate
          : undefined,
    });
    revalidatePath("/algorithms/queue");
  }

  async function rejectAction(formData: FormData) {
    "use server";
    const id = String(formData.get("id") ?? "").trim();
    const reason = String(formData.get("reason") ?? "").trim();
    if (!id) return;
    const tenant2 = await requireTenantContext();
    if (!tenant2) redirect("/login");
    await rejectAlgorithm(tenant2.organizationId, id, reason);
    revalidatePath("/algorithms/queue");
  }

  async function mergeAction(formData: FormData) {
    "use server";
    const id = String(formData.get("id") ?? "").trim();
    const intoId = String(formData.get("intoId") ?? "").trim();
    if (!id || !intoId) return;
    const tenant2 = await requireTenantContext();
    if (!tenant2) redirect("/login");
    await mergeAlgorithm(tenant2.organizationId, id, intoId);
    revalidatePath("/algorithms/queue");
  }

  return (
    <main
      style={{
        maxWidth: "1080px",
        margin: "0 auto",
        padding: "2.75rem 2rem",
      }}
    >
      <header style={{ marginBottom: "1.75rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.12em",
            margin: 0,
          }}
        >
          Algorithms · triage queue
        </h1>
        <p
          className="mono"
          data-testid="algorithms-queue-count"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.24em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginTop: "0.4rem",
          }}
        >
          {rows.length} awaiting review
        </p>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            color: "var(--parchment-dim)",
            marginTop: "0.75rem",
            maxWidth: "44em",
            lineHeight: 1.55,
          }}
        >
          Each draft is a candidate logical function the agent proposed
          from a cluster of principles. Accept (with optional edits) to
          promote to <code>ACTIVE</code>, reject with a reason, or merge
          into an existing algorithm. The agent never auto-promotes —
          every publish is a founder action.
        </p>
      </header>

      {rows.length === 0 ? (
        <p
          className="mono"
          data-testid="algorithms-queue-empty"
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.8rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            padding: "2rem 0",
          }}
        >
          No drafts in the queue.
        </p>
      ) : (
        <QueueClient
          rows={rows as AlgorithmRow[]}
          acceptAction={acceptAction}
          rejectAction={rejectAction}
          mergeAction={mergeAction}
        />
      )}
    </main>
  );
}
