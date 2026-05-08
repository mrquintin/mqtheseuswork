/**
 * Public belief-revision detail page.
 *
 * Linked from the "updated" pill on any public article whose underlying
 * conclusion was revised. We render the diff in plain prose: previously
 * concluded X with confidence Y; new evidence Z changed it to ….
 *
 * Why public: a revision is itself a publishable epistemic event — a
 * footnote-grade change to a published claim. Hiding revisions behind
 * the auth wall would let the firm silently mutate its public record;
 * the audit trail makes that impossible by design.
 *
 * Reverted events still render (the URL stays valid forever), but they
 * carry a "Reverted" banner and the revision is treated as no-op for
 * the conclusion's current pill state.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { db } from "@/lib/db";
import {
  getRevisionEvent,
  renderRevisionProse,
  type RevisionEventDTO,
} from "@/lib/revisionApi";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type PageProps = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const event = await getRevisionEvent(id);
  if (!event) return { title: "Revision not found" };
  return {
    title: `Belief revision · ${event.id.slice(0, 8)}`,
    description: `Revision affecting ${event.affectedConclusionIds.length} conclusion(s).`,
  };
}

export default async function RevisionDetailPage({ params }: PageProps) {
  const { id } = await params;
  const event = await getRevisionEvent(id);
  if (!event) notFound();

  const conclusionTexts = await loadConclusionTexts(
    event.organizationId,
    event.affectedConclusionIds,
  );
  const prose = renderRevisionProse(event, conclusionTexts);
  const reverted = event.revertedAt !== null;

  return (
    <main className="revision-detail-page">
      <header>
        <p className="revision-detail-eyebrow">Belief revision</p>
        <h1>Revision {event.id.slice(0, 8)}</h1>
        <p className="revision-detail-meta">
          Committed {new Date(event.createdAt).toLocaleString()} ·{" "}
          {event.affectedConclusionIds.length} conclusion
          {event.affectedConclusionIds.length === 1 ? "" : "s"} affected
          {event.typedConfirmation ? " · typed-confirmation gate" : null}
        </p>
        {reverted ? (
          <div className="revision-detail-reverted-banner" role="status">
            This revision was reverted on{" "}
            {new Date(event.revertedAt!).toLocaleString()}. The diff below is
            kept for the audit record; it does not reflect current beliefs.
          </div>
        ) : null}
      </header>

      <section className="revision-detail-prose">
        {prose.length === 0 ? (
          <p>This revision did not move any conclusion above the δ threshold.</p>
        ) : (
          prose.map((line, i) => <p key={i}>{line}</p>)
        )}
      </section>

      <section className="revision-detail-inputs">
        <h2>Evidence inputs</h2>
        <ul>
          {event.inputs.map((input, i) => (
            <li key={`${input.claimId}:${i}`}>
              <code>{input.claimId}</code> · weight {input.weight.toFixed(2)} ·{" "}
              <em>{input.newEvidence}</em>
            </li>
          ))}
        </ul>
      </section>

      <RevisedConclusionsList event={event} conclusionTexts={conclusionTexts} />

      <footer className="revision-detail-footer">
        <Link href="/">← Back to homepage</Link>
      </footer>
    </main>
  );
}

function RevisedConclusionsList({
  event,
  conclusionTexts,
}: {
  event: RevisionEventDTO;
  conclusionTexts: Record<string, string>;
}) {
  const all = [
    ...event.plan.newlyContradicted.map((s) => ({ ...s, bucket: "Newly contradicted" })),
    ...event.plan.newlySupported.map((s) => ({ ...s, bucket: "Newly supported" })),
    ...event.plan.changed.map((s) => ({ ...s, bucket: "Confidence changed" })),
  ];
  if (all.length === 0) return null;
  return (
    <section className="revision-detail-table">
      <h2>Affected conclusions</h2>
      <table>
        <thead>
          <tr>
            <th>Conclusion</th>
            <th>Bucket</th>
            <th>Before</th>
            <th>After</th>
          </tr>
        </thead>
        <tbody>
          {all.map((row) => (
            <tr key={row.conclusionId}>
              <td>{conclusionTexts[row.conclusionId] ?? row.conclusionId}</td>
              <td>{row.bucket}</td>
              <td>{row.before.toFixed(2)}</td>
              <td>{row.after.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

async function loadConclusionTexts(
  organizationId: string,
  ids: string[],
): Promise<Record<string, string>> {
  if (ids.length === 0) return {};
  // The `affectedConclusionIds` payload contains cascade node ids, which
  // we map back to Conclusion rows via `noosphereId`. Conclusions that
  // can't be resolved fall through to their raw id in the renderer.
  const rows = await db.conclusion.findMany({
    where: {
      organizationId,
      OR: [
        { id: { in: ids } },
        { noosphereId: { in: ids } },
      ],
    },
    select: { id: true, noosphereId: true, text: true },
  });
  const out: Record<string, string> = {};
  for (const r of rows) {
    out[r.id] = r.text;
    if (r.noosphereId) out[r.noosphereId] = r.text;
  }
  return out;
}
