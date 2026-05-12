import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { submitToRigorGate } from "@/lib/api/round3";
import { callNoosphereJson } from "@/lib/pythonRuntime";
import { founderDisplayName } from "@/lib/founderDisplay";

/**
 * Primary action row for /conclusions/[id].
 *
 * Round 20 trims the bar to the two highest-frequency operator actions:
 *
 *   - Run peer review       (primary CTA, solid)
 *   - Queue for publication (secondary, outline)
 *
 * Peer review history and the decay dashboard now live inside the
 * Diagnostics disclosure on the page, alongside the export link. The
 * server actions stay as before so existing keymap / form contracts
 * keep working.
 */
export default function ActionsBar({
  conclusionId,
  canWrite,
}: {
  conclusionId: string;
  canWrite: boolean;
}) {
  async function runPeerReview() {
    "use server";
    const founder = await getFounder();
    if (!founder) redirect("/login");
    const gate = await submitToRigorGate("peer_review.run", founderDisplayName(founder));
    if (!gate.approved) {
      redirect(
        `/conclusions/${conclusionId}?tab=peer&ledger=${encodeURIComponent(
          `rejected:${gate.reason || "rigor gate"}`,
        )}`,
      );
    }
    await callNoosphereJson(
      ["peer-review", "--conclusion-id", conclusionId],
      "Peer review run failed",
    );
    revalidatePath(`/conclusions/${conclusionId}`);
    redirect(`/conclusions/${conclusionId}?tab=peer`);
  }

  async function queueForPublication() {
    "use server";
    const founder = await getFounder();
    if (!founder) redirect("/login");

    const existing = await db.publicationReview.findFirst({
      where: {
        organizationId: founder.organizationId,
        conclusionId,
      },
      orderBy: { createdAt: "desc" },
    });
    if (!existing || existing.status === "declined" || existing.status === "needs_revision") {
      await db.publicationReview.create({
        data: {
          organizationId: founder.organizationId,
          conclusionId,
          status: "queued",
        },
      });
    }
    revalidatePath(`/conclusions/${conclusionId}`);
    redirect(`/conclusions/${conclusionId}?queued=1`);
  }

  const btnStyle: React.CSSProperties = { fontSize: "0.65rem", textDecoration: "none" };

  return (
    <div
      role="group"
      aria-label="Primary actions"
      style={{
        display: "flex",
        gap: "0.5rem",
        flexWrap: "wrap",
        alignItems: "center",
        padding: "0.5rem 0",
        marginBottom: "0.5rem",
      }}
    >
      <form action={runPeerReview}>
        <button
          type="submit"
          className="btn-solid btn"
          style={btnStyle}
          disabled={!canWrite}
        >
          Run peer review
        </button>
      </form>
      <form action={queueForPublication}>
        <button
          type="submit"
          className="btn"
          style={btnStyle}
          disabled={!canWrite}
        >
          Queue for publication
        </button>
      </form>
    </div>
  );
}
