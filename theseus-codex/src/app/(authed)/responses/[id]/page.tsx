/**
 * Response triage — detail view.
 *
 * Surfaces a single triaged response with the four reply primitives:
 *   - private reply (emails the responder back through the existing pipeline),
 *   - promote to PublicReply (only if the responder consented to publication),
 *   - promote the implied objection to the review queue,
 *   - trigger a revision (prompt 16) when new evidence is genuinely new.
 *
 * The page also lets the founder override the classifier label / spam
 * reason — every classifier output is overrideable, the founder
 * always has the last word.
 */

import Link from "next/link";
import { notFound } from "next/navigation";

import {
  TRIAGE_LABELS,
  getReplyBody,
  getTriageDetail,
} from "@/lib/responseTriageApi";
import { requireTenantContext } from "@/lib/tenant";

import {
  archiveTriageAction,
  overrideTriageLabelAction,
  promotePublicReplyAction,
  promoteToReviewAction,
  replyPrivateAction,
  restoreTriageAction,
  triggerRevisionAction,
} from "../triageActions";

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ id: string }> };

export default async function ResponseDetailPage({ params }: PageProps) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const { id } = await params;
  const row = await getTriageDetail(tenant.organizationId, id);
  if (!row) notFound();

  const replyBody = (await getReplyBody(tenant.organizationId, id)) ?? "";
  const archived = row.archivedAt !== null;
  const canPublish = row.publicResponse.publishConsent;
  const canPrivateReply = !row.publicResponse.pseudonymous && Boolean(row.publicResponse.submitterEmail);

  return (
    <main style={{ maxWidth: "880px", margin: "0 auto", padding: "3rem 2rem" }}>
      <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem", letterSpacing: "0.22em", margin: 0, textTransform: "uppercase" }}>
        <Link href="/responses/queue" style={{ color: "var(--amber-dim)" }}>← Queue</Link>
      </p>
      <h1 style={{ color: "var(--amber)", fontFamily: "'Cinzel Decorative', serif", fontSize: "1.4rem", letterSpacing: "0.16em", margin: "0.4rem 0 0.6rem", textShadow: "var(--glow-md)" }}>
        Response on {row.conclusion.title || row.conclusion.slug}
      </h1>
      <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", letterSpacing: "0.18em", margin: 0, textTransform: "uppercase" }}>
        {row.effectiveLabel.replace("_", " ")} · severity {row.severityValue.toFixed(2)} · confidence {row.confidence.toFixed(2)}
        {row.publicResponse.publishConsent ? " · publish-consent" : " · publish-denied"}
        {row.elevatedSenderFlag ? " · repeat sender" : ""}
        {archived ? ` · archived${row.archiveNote ? ` — ${row.archiveNote}` : ""}` : ""}
      </p>

      <section style={card}>
        <h2 style={cardHeading}>Original response</h2>
        <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.65rem", margin: "0 0 0.5rem" }}>
          {row.publicResponse.kind} · {row.publicResponse.pseudonymous ? "Pseudonymous" : row.publicResponse.submitterEmail || "unknown"}
        </p>
        <p style={{ whiteSpace: "pre-wrap", color: "var(--parchment)", margin: 0 }}>
          {row.publicResponse.body}
        </p>
        {row.publicResponse.citationUrl ? (
          <p style={{ marginTop: "0.6rem" }}>
            <a className="mono" href={row.publicResponse.citationUrl} rel="noreferrer" target="_blank" style={{ color: "var(--amber)" }}>
              {row.publicResponse.citationUrl}
            </a>
          </p>
        ) : null}
      </section>

      {row.impliedObjection ? (
        <section style={card}>
          <h2 style={cardHeading}>Implied objection</h2>
          <p style={{ color: "var(--parchment)", fontStyle: "italic", margin: 0 }}>
            {row.impliedObjection}
          </p>
          <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.6rem", margin: "0.45rem 0 0" }}>
            {row.rationale}
          </p>
        </section>
      ) : null}

      <section style={card}>
        <h2 style={cardHeading}>Override classifier</h2>
        <form action={overrideTriageLabelAction} style={{ display: "grid", gap: "0.5rem" }}>
          <input type="hidden" name="triageId" value={row.id} />
          <label className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem" }}>
            Manual label
            <select name="manualLabel" defaultValue="" style={selectStyle}>
              <option value="">(use classifier · {row.label})</option>
              {TRIAGE_LABELS.map((label) => (
                <option key={label} value={label}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <input
            name="manualReason"
            placeholder="optional override note"
            style={selectStyle}
          />
          <button type="submit" className="btn">Save override</button>
        </form>
      </section>

      <section style={card}>
        <h2 style={cardHeading}>Reply privately</h2>
        {canPrivateReply ? (
          <form action={replyPrivateAction} style={{ display: "grid", gap: "0.5rem" }}>
            <input type="hidden" name="triageId" value={row.id} />
            <textarea name="body" rows={5} defaultValue={replyBody} required style={textareaStyle} />
            <button type="submit" className="btn">Send private reply</button>
          </form>
        ) : (
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
            Cannot reply privately — the responder is pseudonymous or did not provide an email.
          </p>
        )}
      </section>

      <section style={card}>
        <h2 style={cardHeading}>Publish reply on the article</h2>
        {canPublish ? (
          <form action={promotePublicReplyAction} style={{ display: "grid", gap: "0.5rem" }}>
            <input type="hidden" name="triageId" value={row.id} />
            <textarea name="body" rows={5} defaultValue={replyBody} required style={textareaStyle} />
            <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.6rem", margin: 0 }}>
              The responder consented to publication when they submitted. Confirming here adds the
              response + reply to the article&apos;s &quot;Reader responses&quot; appendix.
            </p>
            <button type="submit" className="btn">Confirm and publish</button>
          </form>
        ) : (
          <p style={{ color: "var(--parchment-dim)", margin: 0 }}>
            Responder did not consent to publication. Use the private reply primitive instead.
          </p>
        )}
      </section>

      <section style={card}>
        <h2 style={cardHeading}>Promote to review queue</h2>
        <form action={promoteToReviewAction} style={{ display: "grid", gap: "0.5rem" }}>
          <input type="hidden" name="triageId" value={row.id} />
          <input name="note" placeholder="optional note for the reviewer" style={selectStyle} />
          <button type="submit" className="btn" disabled={!row.impliedObjection}>
            {row.impliedObjection ? "Promote implied objection" : "(no implied objection)"}
          </button>
        </form>
      </section>

      <section style={card}>
        <h2 style={cardHeading}>Trigger revision (prompt 16)</h2>
        <form action={triggerRevisionAction} style={{ display: "grid", gap: "0.5rem" }}>
          <input type="hidden" name="triageId" value={row.id} />
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
            Weight in [-1, +1]. Negative = the response contradicts the claim; positive = it
            corroborates. The revision engine computes the impact preview before any commit.
          </p>
          <button type="submit" className="btn" disabled={!row.impliedObjection}>
            {row.impliedObjection ? "Route to revision engine" : "(no implied objection)"}
          </button>
        </form>
      </section>

      <section style={card}>
        <h2 style={cardHeading}>Archive</h2>
        {archived ? (
          <form action={restoreTriageAction}>
            <input type="hidden" name="triageId" value={row.id} />
            <button type="submit" className="btn">Restore from archive</button>
          </form>
        ) : (
          <form action={archiveTriageAction} style={{ display: "grid", gap: "0.5rem" }}>
            <input type="hidden" name="triageId" value={row.id} />
            <input name="archiveNote" placeholder="archive reason (optional)" style={selectStyle} />
            <button type="submit" className="btn">Archive</button>
          </form>
        )}
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
