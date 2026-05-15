import { redirect } from "next/navigation";
import Link from "next/link";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

import CapturesClient, {
  type CaptureRow,
  type CapturePrinciple,
} from "./CapturesClient";

export const dynamic = "force-dynamic";

/**
 * /captures — voice-memo triage queue.
 *
 * Shows the founder's voice memos top-to-bottom (newest first), each
 * row carrying:
 *   • recorded-at timestamp;
 *   • transcript (or extraction status if Whisper hasn't run yet);
 *   • the principle extractions inlined under the transcript with
 *     accept-as-is / edit-then-accept / reject controls;
 *   • a "play audio" affordance backed by `<audio>` pointing at the
 *     Upload row's public audio URL — so the founder can re-listen
 *     while reading the candidates;
 *   • a "discard whole capture" with confirmation, identical in shape
 *     to the library row delete (soft-delete via /api/uploads/[id]).
 *
 * Server component fetches; the client island owns the audio player
 * and the per-principle triage actions.
 */
export default async function CapturesPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  // Voice memos are normal Upload rows with `sourceType="voice_memo"`.
  // Quick-capture creates them as `visibility="private"` so peers
  // never see another founder's half-formed thoughts, and we mirror
  // that filter here: a founder only ever reads their own captures.
  const uploads = await db.upload.findMany({
    where: {
      organizationId: tenant.organizationId,
      founderId: tenant.founderId,
      sourceType: "voice_memo",
      deletedAt: null,
    },
    orderBy: { createdAt: "desc" },
    take: 60,
    select: {
      id: true,
      title: true,
      createdAt: true,
      status: true,
      audioUrl: true,
      audioDurationSec: true,
      textContent: true,
      extractionMethod: true,
      errorMessage: true,
    },
  });

  const uploadIds = uploads.map((u) => u.id);
  const sources = uploadIds.length
    ? await db.conclusionSource.findMany({
        where: { uploadId: { in: uploadIds } },
        select: { uploadId: true, conclusionId: true },
      })
    : [];
  const conclusionIds = Array.from(new Set(sources.map((s) => s.conclusionId)));
  const conclusions = conclusionIds.length
    ? await db.conclusion.findMany({
        where: {
          id: { in: conclusionIds },
          organizationId: tenant.organizationId,
        },
        select: {
          id: true,
          text: true,
          confidenceTier: true,
          principleKind: true,
          sourceSpan: true,
          domainOfApplicability: true,
        },
      })
    : [];
  const concById = new Map(conclusions.map((c) => [c.id, c]));

  const rows: CaptureRow[] = uploads.map((u) => {
    const principles: CapturePrinciple[] = sources
      .filter((s) => s.uploadId === u.id)
      .map((s) => concById.get(s.conclusionId))
      .filter((c): c is NonNullable<typeof c> => Boolean(c))
      .map((c) => ({
        id: c.id,
        text: c.text,
        confidenceTier: c.confidenceTier,
        principleKind: c.principleKind ?? null,
        sourceSpan: c.sourceSpan ?? null,
        domainOfApplicability: c.domainOfApplicability ?? null,
      }));
    return {
      id: u.id,
      title: u.title,
      createdAtIso: u.createdAt.toISOString(),
      status: u.status,
      audioUrl: u.audioUrl,
      audioDurationSec: u.audioDurationSec,
      transcript: u.textContent,
      extractionMethod: u.extractionMethod,
      errorMessage: u.errorMessage,
      principles,
    };
  });

  return (
    <main
      style={{
        maxWidth: "920px",
        margin: "0 auto",
        padding: "2.5rem 1.5rem 4rem",
      }}
    >
      <header style={{ marginBottom: "1.5rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.12em",
            margin: 0,
            fontSize: "1.75rem",
          }}
        >
          Captures · voice memos
        </h1>
        <p
          style={{
            margin: "0.45rem 0 0",
            color: "rgba(0,0,0,0.62)",
            fontSize: "0.92rem",
            lineHeight: 1.5,
            maxWidth: "62ch",
          }}
        >
          Quick-record sessions, oldest claim at the bottom. Each
          captured memo is transcribed, then a principle extractor
          tuned for stream-of-consciousness input proposes principles
          for your review. Nothing leaves this page without your
          explicit accept.
        </p>
      </header>

      {rows.length === 0 ? (
        <EmptyState />
      ) : (
        <CapturesClient rows={rows} />
      )}
    </main>
  );
}

function EmptyState() {
  return (
    <div
      style={{
        padding: "2rem 1.5rem",
        textAlign: "center",
        border: "1px dashed rgba(0,0,0,0.18)",
        borderRadius: 10,
        color: "rgba(0,0,0,0.62)",
      }}
    >
      <p style={{ margin: 0, fontSize: "0.95rem" }}>
        No voice memos yet. Press <strong>Cmd+Shift+R</strong> from
        any authed page — or click the <em>Quick record</em> button in
        the bottom-right corner — to capture a stream of consciousness.
      </p>
      <p
        style={{
          marginTop: "0.75rem",
          fontSize: "0.85rem",
          color: "rgba(0,0,0,0.5)",
        }}
      >
        <Link href="/dashboard" style={{ color: "#1d4ed8" }}>
          Back to dashboard →
        </Link>
      </p>
    </div>
  );
}
