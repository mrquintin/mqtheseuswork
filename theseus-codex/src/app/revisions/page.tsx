import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata: Metadata = {
  title: "Revisions",
  description:
    "Public explanation of Theseus revision events and how changed conclusions remain auditable.",
};

export const dynamic = "force-dynamic";

async function isFounderAuthed(): Promise<boolean> {
  try {
    return Boolean(await getFounder());
  } catch {
    return false;
  }
}

export default async function RevisionsIndexPage() {
  const authed = await isFounderAuthed();

  return (
    <>
      <PublicHeader authed={authed} />
      <main className="public-container" style={{ padding: "2.5rem 1.5rem" }}>
        <section className="public-section" aria-labelledby="revisions-title">
          <p className="mono public-eyebrow">Revisions</p>
          <h1 id="revisions-title" className="public-title">
            Revision ledger
          </h1>
          <p className="public-lede">
            Theseus treats changes of mind as part of the record. A revision
            event should explain the evidence that moved, the conclusions that
            changed, and the confidence delta that followed.
          </p>
        </section>

        <section className="public-section" aria-labelledby="revisions-how">
          <h2 id="revisions-how" className="public-section-title">
            What a revision page contains
          </h2>
          <div className="public-card-grid">
            <article className="public-card">
              <span className="mono public-card-kicker">Inputs</span>
              <strong>Evidence that changed</strong>
              <span>
                Revision detail pages list the source inputs and weights that
                triggered a material update.
              </span>
            </article>
            <article className="public-card">
              <span className="mono public-card-kicker">Outputs</span>
              <strong>Conclusions affected</strong>
              <span>
                Each revised conclusion is linked back to its public or founder
                surface so the causal trail remains navigable.
              </span>
            </article>
            <article className="public-card">
              <span className="mono public-card-kicker">Integrity</span>
              <strong>Proof and signatures</strong>
              <span>
                Publication signatures and revision records are cross-checks;
                neither should silently overwrite the other.
              </span>
            </article>
          </div>
          <p className="public-muted" style={{ marginTop: "1.25rem" }}>
            Individual revision events are addressable at{" "}
            <code>/revisions/&lt;event-id&gt;</code>. When no public event is
            selected, this index keeps the route meaningful rather than falling
            through to a 404.
          </p>
          <p style={{ marginTop: "1rem" }}>
            <Link className="public-inline-link" href="/proof">
              Read the publication proof contract
            </Link>
          </p>
        </section>
      </main>
    </>
  );
}
