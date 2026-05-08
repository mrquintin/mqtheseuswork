/**
 * Critique detail — moderation actions + bounty workflow.
 *
 * One page; the founder picks one of three terminal decisions
 * (accept / partial / reject) and, when accepting, optionally queues
 * a high-severity bounty payout. Bounty confirmation is its own form
 * because it's the founder's *second* opt-in — the codex does not
 * pay out without it.
 *
 * Optional follow-ups (revision engine + addendum) live in their own
 * sections so they remain explicit one-shot actions, not implicit
 * side effects of acceptance.
 */

import Link from "next/link";
import { notFound } from "next/navigation";

import { critiqueDisplayName, getCritique } from "@/lib/critiquesApi";
import { requireTenantContext } from "@/lib/tenant";

import {
  acceptCritiqueAction,
  archiveCritiqueAction,
  attachAddendumAction,
  cancelBountyAction,
  confirmBountyAction,
  partialCritiqueAction,
  rejectCritiqueAction,
  triggerCritiqueRevisionAction,
} from "../actions";

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ id: string }> };

export default async function CritiqueDetailPage({ params }: PageProps) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  const { id } = await params;

  const row = await getCritique(tenant.organizationId, id);
  if (!row) notFound();

  const credit = critiqueDisplayName(row);
  const isPending = row.status === "pending";
  const isAccepted = row.status === "accepted";
  const isHighSeverity = row.severityLabel === "high";
  const bounty = row.bounty;

  return (
    <main style={{ maxWidth: "920px", margin: "0 auto", padding: "3rem 2rem" }}>
      <p
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.62rem",
          letterSpacing: "0.22em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        <Link href="/critiques/queue" style={{ color: "var(--amber-dim)" }}>← Queue</Link>
      </p>
      <h1
        style={{
          color: "var(--amber)",
          fontFamily: "'Cinzel Decorative', serif",
          fontSize: "1.4rem",
          letterSpacing: "0.16em",
          margin: "0.4rem 0 0.6rem",
          textShadow: "var(--glow-md)",
        }}
      >
        Critique on {row.articleSlug}
      </h1>
      <p
        className="mono"
        style={{
          color: "var(--amber-dim)",
          fontSize: "0.6rem",
          letterSpacing: "0.18em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        {row.status}
        {row.severityLabel ? ` · severity ${row.severityLabel} (${row.severityValue.toFixed(2)})` : ""}
        {bounty ? ` · bounty ${bounty.status}` : ""}
      </p>

      <section style={card}>
        <h2 style={cardHeading}>Critic</h2>
        <p style={{ color: "var(--parchment)", margin: 0 }}>
          {credit}
          {row.publicUrl ? (
            <>
              {" — "}
              <a href={row.publicUrl} rel="noreferrer" target="_blank" style={{ color: "var(--amber)" }}>
                {row.publicUrl}
              </a>
            </>
          ) : null}
        </p>
        <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.65rem", margin: "0.4rem 0 0" }}>
          {row.submitterEmail}
          {row.orcid ? ` · ORCID ${row.orcid}` : ""}
        </p>
        {row.bio ? (
          <p style={{ color: "var(--parchment-dim)", margin: "0.4rem 0 0", fontStyle: "italic" }}>
            {row.bio}
          </p>
        ) : null}
      </section>

      <section style={card}>
        <h2 style={cardHeading}>Targeted claim</h2>
        <p style={{ color: "var(--parchment)", margin: 0, whiteSpace: "pre-wrap" }}>
          {row.targetClaim}
        </p>
      </section>

      <section style={card}>
        <h2 style={cardHeading}>Counter-evidence</h2>
        <p style={{ color: "var(--parchment)", margin: 0, whiteSpace: "pre-wrap" }}>
          {row.counterEvidence}
        </p>
      </section>

      <section style={card}>
        <h2 style={cardHeading}>Method used</h2>
        <p style={{ color: "var(--parchment)", margin: 0, whiteSpace: "pre-wrap" }}>
          {row.derivationMethod}
        </p>
      </section>

      {row.citations ? (
        <section style={card}>
          <h2 style={cardHeading}>Citations</h2>
          <pre style={{ color: "var(--parchment)", margin: 0, whiteSpace: "pre-wrap" }}>
            {row.citations}
          </pre>
        </section>
      ) : null}

      {row.moderatorNote ? (
        <section style={card}>
          <h2 style={cardHeading}>Moderator note</h2>
          <p style={{ color: "var(--parchment-dim)", margin: 0, whiteSpace: "pre-wrap" }}>
            {row.moderatorNote}
          </p>
        </section>
      ) : null}

      {isPending ? (
        <>
          <section style={card}>
            <h2 style={cardHeading}>Accept critique</h2>
            <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", margin: "0 0 0.5rem" }}>
              Publishes alongside the article with credit. Severity = high makes the
              bounty payout eligible (you still confirm payout separately).
            </p>
            <form action={acceptCritiqueAction} style={{ display: "grid", gap: "0.5rem" }}>
              <input type="hidden" name="critiqueId" value={row.id} />
              <label className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem" }}>
                Severity label
                <select name="severityLabel" defaultValue="medium" style={selectStyle} required>
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high (bounty-eligible)</option>
                </select>
              </label>
              <input
                name="severityValue"
                type="number"
                step="0.01"
                min={0}
                max={1}
                defaultValue={0.5}
                placeholder="severity value [0,1]"
                style={selectStyle}
              />
              <textarea
                name="moderatorNote"
                placeholder="optional note (recorded; shown to the critic in the acceptance email)"
                rows={3}
                style={textareaStyle}
              />
              <label className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem" }}>
                <input type="checkbox" name="queueBounty" value="1" defaultChecked /> Queue bounty
                payout if severity = high
              </label>
              <input
                name="bountyAmountUsd"
                type="number"
                min={0}
                max={100000}
                defaultValue={500}
                style={selectStyle}
              />
              <label className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem" }}>
                Payout mode
                <select name="bountyPayoutMode" defaultValue="self" style={selectStyle}>
                  <option value="self">to critic</option>
                  <option value="charity">donate to charity (critic chose)</option>
                </select>
              </label>
              <input
                name="bountyDestination"
                placeholder="charity name / URL (only for charity mode)"
                style={selectStyle}
              />
              <button type="submit" className="btn">Accept and (maybe) queue bounty</button>
            </form>
          </section>

          <section style={card}>
            <h2 style={cardHeading}>Mark as partial (private discussion)</h2>
            <form action={partialCritiqueAction} style={{ display: "grid", gap: "0.5rem" }}>
              <input type="hidden" name="critiqueId" value={row.id} />
              <textarea
                name="moderatorNote"
                placeholder="why this is partial — emailed to the critic"
                rows={3}
                style={textareaStyle}
                required
              />
              <button type="submit" className="btn">Mark partial</button>
            </form>
          </section>

          <section style={card}>
            <h2 style={cardHeading}>Reject</h2>
            <form action={rejectCritiqueAction} style={{ display: "grid", gap: "0.5rem" }}>
              <input type="hidden" name="critiqueId" value={row.id} />
              <textarea
                name="moderatorNote"
                placeholder="reason — surfaced in the rejection email"
                rows={3}
                style={textareaStyle}
                required
              />
              <button type="submit" className="btn">Reject</button>
            </form>
          </section>
        </>
      ) : null}

      {isAccepted ? (
        <>
          {isHighSeverity && bounty ? (
            <section style={card}>
              <h2 style={cardHeading}>Bounty payout · {bounty.status}</h2>
              <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", margin: "0 0 0.5rem" }}>
                Amount ${bounty.amountUsd} · mode {bounty.payoutMode} · destination{" "}
                {bounty.destination || "(critic email of record)"}
              </p>
              {bounty.status === "pending_founder_confirmation" ? (
                <>
                  <form action={confirmBountyAction} style={{ display: "grid", gap: "0.5rem" }}>
                    <input type="hidden" name="critiqueId" value={row.id} />
                    <input
                      name="externalRef"
                      placeholder="optional payouts-pipeline reference id"
                      style={selectStyle}
                    />
                    <p className="mono" style={{ color: "var(--amber)", fontSize: "0.6rem", margin: 0 }}>
                      Confirming flips the row to `confirmed`. The codex still does not send
                      money — your firm&apos;s payouts pipeline is the eventual sender.
                    </p>
                    <button type="submit" className="btn">Confirm payout</button>
                  </form>
                  <form action={cancelBountyAction} style={{ display: "grid", gap: "0.5rem", marginTop: "0.6rem" }}>
                    <input type="hidden" name="critiqueId" value={row.id} />
                    <input
                      name="cancellationNote"
                      placeholder="cancellation reason"
                      style={selectStyle}
                    />
                    <button type="submit" className="btn">Cancel queued payout</button>
                  </form>
                </>
              ) : (
                <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
                  {bounty.status === "confirmed"
                    ? `Confirmed at ${bounty.confirmedAt?.toISOString() ?? "—"}${bounty.externalRef ? ` · ref ${bounty.externalRef}` : ""}`
                    : `Cancelled${bounty.cancellationNote ? ` — ${bounty.cancellationNote}` : ""}`}
                </p>
              )}
            </section>
          ) : null}

          <section style={card}>
            <h2 style={cardHeading}>Trigger revision (prompt 16)</h2>
            <form action={triggerCritiqueRevisionAction} style={{ display: "grid", gap: "0.5rem" }}>
              <input type="hidden" name="critiqueId" value={row.id} />
              <input name="claimId" placeholder="claim id to revise" required style={selectStyle} />
              <input
                name="weight"
                type="number"
                step="0.1"
                min={-1}
                max={1}
                defaultValue={-0.5}
                style={selectStyle}
              />
              <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", margin: 0 }}>
                Weight in [-1, +1]. Negative = the critique contradicts the claim. Producing a
                revision keeps the critic in the lineage.
              </p>
              <button type="submit" className="btn" disabled={Boolean(row.triggeredRevisionId)}>
                {row.triggeredRevisionId ? "Already routed" : "Route to revision engine"}
              </button>
            </form>
          </section>

          <section style={card}>
            <h2 style={cardHeading}>Update article via addendum (prompt 43)</h2>
            <form action={attachAddendumAction} style={{ display: "grid", gap: "0.5rem" }}>
              <input type="hidden" name="critiqueId" value={row.id} />
              <input
                name="summary"
                placeholder="one-line addendum summary (shown publicly)"
                required
                style={selectStyle}
              />
              <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", margin: 0 }}>
                The critic&apos;s name and contribution are tracked in the addendum body so
                the lineage stays honest about what changed and why.
              </p>
              <button type="submit" className="btn" disabled={Boolean(row.addendumId)}>
                {row.addendumId ? "Addendum already attached" : "Publish addendum"}
              </button>
            </form>
          </section>
        </>
      ) : null}

      <section style={card}>
        <h2 style={cardHeading}>Archive</h2>
        <form action={archiveCritiqueAction} style={{ display: "grid", gap: "0.5rem" }}>
          <input type="hidden" name="critiqueId" value={row.id} />
          <input name="moderatorNote" placeholder="archive reason (optional)" style={selectStyle} />
          <button type="submit" className="btn">Archive</button>
        </form>
      </section>
    </main>
  );
}

const card = {
  background: "rgba(20, 20, 26, 0.45)",
  border: "1px solid var(--border)",
  borderRadius: "0.4rem",
  margin: "1.2rem 0 0",
  padding: "1.1rem 1.2rem",
};

const cardHeading = {
  color: "var(--amber-dim)",
  fontSize: "0.7rem",
  letterSpacing: "0.18em",
  margin: "0 0 0.6rem",
  textTransform: "uppercase" as const,
};

const selectStyle = {
  background: "transparent",
  border: "1px solid var(--border)",
  color: "var(--parchment)",
  fontFamily: "inherit",
  padding: "0.35rem 0.45rem",
  width: "100%",
};

const textareaStyle = {
  ...selectStyle,
  minHeight: "5rem",
  resize: "vertical" as const,
};
