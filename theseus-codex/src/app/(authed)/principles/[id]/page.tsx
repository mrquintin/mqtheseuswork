import Link from "next/link";
import { redirect, notFound } from "next/navigation";
import { revalidatePath } from "next/cache";

import { getFounder } from "@/lib/auth";
import {
  acceptPrinciple,
  getPrinciple,
  hydrateClusterConclusions,
  listAcceptedPrinciples,
  mergePrinciple,
  rejectPrinciple,
} from "@/lib/principlesApi";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

type Params = { id: string };

/**
 * Founder triage detail page.
 *
 * Three actions, each as a server action:
 *
 *   accept — founder edits the text + domains, optionally flips the
 *            public-visible flag. Public visibility requires ≥1 domain.
 *   reject — founder declines; the reason is stored on the row.
 *   merge  — folds this principle into an existing accepted one; the
 *            row stays in the table as a tombstone with mergedIntoId.
 *
 * The cluster conclusions and the LLM-cited subset are rendered side
 * by side so the reviewer reads the candidate next to the evidence.
 */
export default async function PrincipleDetailPage({
  params,
}: {
  params: Promise<Params>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const { id } = await params;
  const principle = await getPrinciple(tenant.organizationId, id);
  if (!principle) notFound();

  const [clusterConclusions, mergeTargets] = await Promise.all([
    hydrateClusterConclusions(
      tenant.organizationId,
      principle.clusterConclusionIds,
    ),
    listAcceptedPrinciples(tenant.organizationId, principle.id),
  ]);
  const citedSet = new Set(principle.citedConclusionIds);

  async function accept(formData: FormData) {
    "use server";
    const founder = await getFounder();
    if (!founder) redirect("/login");
    const text = String(formData.get("text") ?? "").trim();
    const domainsRaw = String(formData.get("domains") ?? "");
    const publicVisible = formData.get("publicVisible") === "on";
    const domains = domainsRaw
      .split(",")
      .map((d) => d.trim())
      .filter(Boolean);
    if (!text) return;
    await acceptPrinciple(founder.organizationId, id, founder.id, {
      text,
      domains,
      publicVisible,
    });
    revalidatePath("/principles/queue");
    revalidatePath(`/principles/${id}`);
    redirect("/principles/queue");
  }

  async function reject(formData: FormData) {
    "use server";
    const founder = await getFounder();
    if (!founder) redirect("/login");
    const reason = String(formData.get("reason") ?? "").trim();
    await rejectPrinciple(founder.organizationId, id, founder.id, reason);
    revalidatePath("/principles/queue");
    revalidatePath(`/principles/${id}`);
    redirect("/principles/queue");
  }

  async function merge(formData: FormData) {
    "use server";
    const founder = await getFounder();
    if (!founder) redirect("/login");
    const intoId = String(formData.get("mergeIntoId") ?? "").trim();
    if (!intoId) return;
    await mergePrinciple(founder.organizationId, id, founder.id, intoId);
    revalidatePath("/principles/queue");
    revalidatePath(`/principles/${id}`);
    redirect("/principles/queue");
  }

  return (
    <main
      style={{
        maxWidth: "920px",
        margin: "0 auto",
        padding: "2.75rem 2rem",
      }}
    >
      <p style={{ marginBottom: "1.25rem" }}>
        <Link
          href="/principles/queue"
          className="mono"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.24em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            textDecoration: "none",
          }}
        >
          ← back to queue
        </Link>
      </p>

      <header style={{ marginBottom: "1.75rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.1em",
            margin: 0,
            fontSize: "1.5rem",
          }}
        >
          Principle · {principle.status}
        </h1>
        <div
          className="mono"
          style={{
            marginTop: "0.5rem",
            fontSize: "0.65rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--parchment-dim)",
            display: "flex",
            flexWrap: "wrap",
            gap: "0.75rem",
          }}
        >
          <span>conviction · {principle.convictionScore.toFixed(2)}</span>
          <span>cluster · {principle.clusterConclusionIds.length}</span>
          <span>domains · {principle.domainBreadth}</span>
          <span>
            centroid · {principle.clusterCentroidSimilarity.toFixed(2)}
          </span>
          {principle.driftReason ? (
            <span style={{ color: "var(--ember, #c0392b)" }}>
              drift · {principle.driftReason}
            </span>
          ) : null}
        </div>
      </header>

      {/* Accept / edit form */}
      <section
        className="portal-card"
        style={{ padding: "1.25rem 1.4rem", marginBottom: "1rem" }}
      >
        <h2
          className="mono"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            margin: 0,
            marginBottom: "0.75rem",
          }}
        >
          Accept (with edits)
        </h2>
        <form action={accept} style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
            <span
              className="mono"
              style={{ fontSize: "0.6rem", letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--parchment-dim)" }}
            >
              Principle text · single sentence the firm is willing to defend
            </span>
            <textarea
              name="text"
              required
              defaultValue={principle.text}
              rows={3}
              style={{
                fontFamily: "'EB Garamond', serif",
                fontSize: "1rem",
                padding: "0.6rem 0.75rem",
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--parchment)",
                resize: "vertical",
              }}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
            <span
              className="mono"
              style={{ fontSize: "0.6rem", letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--parchment-dim)" }}
            >
              Domains · comma-separated; required for public visibility
            </span>
            <input
              type="text"
              name="domains"
              defaultValue={principle.domains.join(", ")}
              style={{
                fontFamily: "'EB Garamond', serif",
                fontSize: "0.95rem",
                padding: "0.5rem 0.75rem",
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--parchment)",
              }}
            />
          </label>
          <label
            className="mono"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              fontSize: "0.65rem",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
            }}
          >
            <input
              type="checkbox"
              name="publicVisible"
              defaultChecked={principle.publicVisible}
            />
            Publish to /methodology/principles
          </label>
          <button
            type="submit"
            className="mono"
            style={{
              alignSelf: "flex-start",
              padding: "0.55rem 1.1rem",
              border: "1px solid var(--amber)",
              color: "var(--amber)",
              background: "transparent",
              fontSize: "0.65rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              cursor: "pointer",
            }}
          >
            Accept principle
          </button>
        </form>
      </section>

      {/* Reject form */}
      <section
        className="portal-card"
        style={{ padding: "1.25rem 1.4rem", marginBottom: "1rem" }}
      >
        <h2
          className="mono"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            margin: 0,
            marginBottom: "0.75rem",
          }}
        >
          Reject (with reason)
        </h2>
        <form action={reject} style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <input
            type="text"
            name="reason"
            placeholder="Why this is not a principle the firm will defend"
            required
            style={{
              fontFamily: "'EB Garamond', serif",
              fontSize: "0.95rem",
              padding: "0.5rem 0.75rem",
              background: "transparent",
              border: "1px solid var(--border)",
              color: "var(--parchment)",
            }}
          />
          <button
            type="submit"
            className="mono"
            style={{
              alignSelf: "flex-start",
              padding: "0.45rem 0.9rem",
              border: "1px solid var(--ember, #c0392b)",
              color: "var(--ember, #c0392b)",
              background: "transparent",
              fontSize: "0.6rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              cursor: "pointer",
            }}
          >
            Reject
          </button>
        </form>
      </section>

      {/* Merge form */}
      {mergeTargets.length > 0 ? (
        <section
          className="portal-card"
          style={{ padding: "1.25rem 1.4rem", marginBottom: "1.5rem" }}
        >
          <h2
            className="mono"
            style={{
              fontSize: "0.7rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              margin: 0,
              marginBottom: "0.75rem",
            }}
          >
            Merge into existing principle
          </h2>
          <form action={merge} style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            <select
              name="mergeIntoId"
              required
              defaultValue=""
              style={{
                padding: "0.5rem 0.75rem",
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--parchment)",
              }}
            >
              <option value="" disabled>
                — choose target —
              </option>
              {mergeTargets.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.text.slice(0, 90)}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="mono"
              style={{
                alignSelf: "flex-start",
                padding: "0.45rem 0.9rem",
                border: "1px solid var(--parchment-dim)",
                color: "var(--parchment-dim)",
                background: "transparent",
                fontSize: "0.6rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                cursor: "pointer",
              }}
            >
              Merge
            </button>
          </form>
        </section>
      ) : null}

      {/* Cluster evidence */}
      <section
        className="portal-card"
        style={{ padding: "1.25rem 1.4rem" }}
      >
        <h2
          className="mono"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            margin: 0,
            marginBottom: "0.75rem",
          }}
        >
          Cluster · {clusterConclusions.length} conclusions
        </h2>
        {clusterConclusions.length === 0 ? (
          <p style={{ color: "var(--parchment-dim)" }}>
            None of the cluster conclusions are present in this org&apos;s
            Codex — they may have been retracted since drafting.
          </p>
        ) : (
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem",
            }}
          >
            {clusterConclusions.map((c) => (
              <li
                key={c.id}
                style={{
                  padding: "0.65rem 0.85rem",
                  border: "1px solid var(--border)",
                  borderLeft: citedSet.has(c.id)
                    ? "3px solid var(--amber)"
                    : "1px solid var(--border)",
                }}
              >
                <Link
                  href={`/conclusions/${c.id}`}
                  style={{
                    color: "var(--parchment)",
                    textDecoration: "none",
                    fontFamily: "'EB Garamond', serif",
                  }}
                >
                  {c.text}
                </Link>
                <div
                  className="mono"
                  style={{
                    marginTop: "0.3rem",
                    fontSize: "0.55rem",
                    letterSpacing: "0.2em",
                    textTransform: "uppercase",
                    color: "var(--parchment-dim)",
                  }}
                >
                  tier · {c.confidenceTier}
                  {citedSet.has(c.id) ? " · cited by draft" : ""}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
