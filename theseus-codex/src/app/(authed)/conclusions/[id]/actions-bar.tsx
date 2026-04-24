import Link from "next/link";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { submitToRigorGate } from "@/lib/api/round3";
import { callNoosphereJson } from "@/lib/pythonRuntime";

/**
 * Actions bar for /conclusions/[id]. Server component; each action
 * uses a `<form action={serverAction}>` so we never fall back to the
 * self-fetching HTTP pattern that broke auth cookie forwarding.
 *
 * Three actions are wired up directly:
 *   - Run peer review       → rigor gate + Noosphere CLI, then hop
 *                              to the Peer review tab.
 *   - Queue for publication → insert a PublicationReview row in
 *                              `queued` status (or keep existing if
 *                              one already exists for this conclusion).
 *
 * Two actions are link-only because they already have dedicated
 * surfaces:
 *   - View decay status
 *   - View full peer review history
 */
export default function ActionsBar({ conclusionId }: { conclusionId: string }) {
  async function runPeerReview() {
    "use server";
    const founder = await getFounder();
    if (!founder) redirect("/login");
    const gate = await submitToRigorGate("peer_review.run", founder.name);
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
      style={{
        display: "flex",
        gap: "0.5rem",
        flexWrap: "wrap",
        padding: "0.5rem 0",
        borderBottom: "1px solid var(--border)",
        marginBottom: "0.75rem",
      }}
    >
      <form action={runPeerReview}>
        <button type="submit" className="btn-solid btn" style={btnStyle}>
          Run peer review
        </button>
      </form>
      <form action={queueForPublication}>
        <button type="submit" className="btn" style={btnStyle}>
          Queue for publication
        </button>
      </form>
      <Link href={`/peer-review/${conclusionId}`} className="btn" style={btnStyle}>
        Peer review history
      </Link>
      <Link href="/decay" className="btn" style={btnStyle}>
        Decay dashboard
      </Link>
    </div>
  );
}
