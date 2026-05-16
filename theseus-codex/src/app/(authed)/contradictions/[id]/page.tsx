import Link from "next/link";
import { notFound } from "next/navigation";
import { db } from "@/lib/db";
import { resolveClaimTexts } from "@/lib/api/round3";
import { requireTenantContext } from "@/lib/tenant";
import EngineActions from "../engine-actions";

/**
 * Per-contradiction detail page — Round 19 prompt 19.
 *
 * The manual "Resolve" path is gone. This page shows:
 *   1. The contradiction itself (the engine's verdict, the two sides).
 *   2. The Lifecycle panel — every transition with the triggering
 *      source, the score change, and the rationale. This is the
 *      source-driven audit trail.
 *   3. The surviving founder actions: ACKNOWLEDGE (sets STANDING) and
 *      DISPUTE (terminal DISPUTED_AS_ERROR).
 *   4. If a synthesis candidate is pending, a triage card linking to
 *      the subsumption queue.
 */

type LifecycleEvent = {
  at: string;
  status_before?: string | null;
  status_after?: string;
  rationale?: string;
  triggering_source_ids?: string[];
  supported_principle_id?: string | null;
  subsuming_principle_id?: string | null;
  score_change?: Record<string, number> | null;
};

function parseEvents(raw: string | null): LifecycleEvent[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed as LifecycleEvent[];
  } catch {
    /* fall through */
  }
  return [];
}

const STATUS_COLOR: Record<string, string> = {
  DETECTED: "var(--amber)",
  STANDING: "var(--amber)",
  WEAKENED: "var(--gold)",
  RESOLVED_BY_SOURCE: "var(--gold)",
  DISPUTED_AS_ERROR: "var(--parchment-dim)",
  SUBSUMED_BY_SYNTHESIS: "var(--gold)",
};

export default async function ContradictionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  const { id } = await params;

  const row = await db.contradiction.findFirst({
    where: { id, organizationId: tenant.organizationId },
  });
  if (!row) {
    notFound();
  }

  const lifecycle = await db.contradictionLifecycle.findUnique({
    where: { contradictionId: id },
  });
  const events = parseEvents(lifecycle?.eventsJson ?? null);

  const claimTexts = await resolveClaimTexts(tenant.organizationId, [
    row.claimAId,
    row.claimBId,
  ]);

  const currentStatus = lifecycle?.currentStatus ?? "DETECTED";
  const statusColor = STATUS_COLOR[currentStatus] ?? "var(--parchment)";
  const pendingCandidate = lifecycle?.pendingSubsumptionPrincipleId ?? null;

  return (
    <main style={{ maxWidth: "880px", margin: "0 auto", padding: "3rem 2rem" }}>
      <Link
        href="/contradictions"
        className="mono"
        style={{
          fontSize: "0.6rem",
          color: "var(--amber-dim)",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          textDecoration: "none",
        }}
      >
        ← All contradictions
      </Link>

      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
          marginTop: "0.5rem",
        }}
      >
        Contradiction
      </h1>

      <div
        className="portal-card"
        style={{ padding: "1.25rem", marginBottom: "1.5rem" }}
      >
        <div
          className="mono"
          style={{
            fontSize: "0.6rem",
            color: "var(--amber-dim)",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Current status
        </div>
        <div
          style={{
            fontSize: "1.1rem",
            color: statusColor,
            fontWeight: "bold",
            letterSpacing: "0.06em",
            marginTop: "0.25rem",
          }}
        >
          {currentStatus.replace(/_/g, " ")}
        </div>
        <p
          style={{
            marginTop: "0.5rem",
            marginBottom: 0,
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "0.85rem",
            color: "var(--parchment-dim)",
            lineHeight: 1.55,
          }}
        >
          Contradictions are not closed by a human clicking a button. They
          persist until new sources strengthen one side, weaken the other,
          or introduce a synthesis principle that subsumes both.
        </p>
      </div>

      <section style={{ marginBottom: "1.5rem" }}>
        <div
          className="mono"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginBottom: "0.5rem",
          }}
        >
          The two principles in tension
        </div>
        <PrincipleCard
          label="A"
          principleId={row.claimAId}
          text={claimTexts[row.claimAId] ?? `Unresolved: ${row.claimAId}`}
          supported={lifecycle?.supportedPrincipleId === row.claimAId}
        />
        <PrincipleCard
          label="B"
          principleId={row.claimBId}
          text={claimTexts[row.claimBId] ?? `Unresolved: ${row.claimBId}`}
          supported={lifecycle?.supportedPrincipleId === row.claimBId}
        />
      </section>

      {pendingCandidate ? (
        <section
          className="portal-card"
          style={{
            padding: "1.25rem",
            marginBottom: "1.5rem",
            borderLeft: "3px solid var(--gold)",
          }}
        >
          <div
            className="mono"
            style={{
              fontSize: "0.65rem",
              color: "var(--gold)",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
          >
            Pending synthesis candidate
          </div>
          <p
            style={{
              marginTop: "0.5rem",
              marginBottom: "0.75rem",
              fontFamily: "'EB Garamond', serif",
              fontSize: "0.95rem",
              color: "var(--parchment)",
              lineHeight: 1.55,
            }}
          >
            The synthesis engine flagged principle{" "}
            <Link
              href={`/conclusions/${pendingCandidate}`}
              style={{ color: "var(--gold)" }}
            >
              {pendingCandidate}
            </Link>{" "}
            as a candidate that may subsume both sides. The agent never
            applies a SUBSUMED transition without founder confirmation —
            triage from the subsumption queue.
          </p>
          <Link
            href="/contradictions/subsumption-queue"
            className="mono btn"
            style={{
              fontSize: "0.65rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
            }}
          >
            Review in subsumption queue →
          </Link>
        </section>
      ) : null}

      <section
        className="portal-card"
        style={{ padding: "1.25rem", marginBottom: "1.5rem" }}
      >
        <div
          className="mono"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginBottom: "0.75rem",
          }}
        >
          Lifecycle
        </div>
        {events.length === 0 ? (
          <p
            style={{
              margin: 0,
              fontStyle: "italic",
              color: "var(--parchment-dim)",
              fontSize: "0.85rem",
            }}
          >
            No transitions yet. The contradiction is in its initial state.
          </p>
        ) : (
          <ol
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.85rem",
            }}
          >
            {events.map((ev, idx) => (
              <LifecycleEventRow key={idx} ev={ev} />
            ))}
          </ol>
        )}
      </section>

      <section style={{ marginBottom: "1.5rem" }}>
        <div
          className="mono"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginBottom: "0.5rem",
          }}
        >
          Founder actions
        </div>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "0.85rem",
            color: "var(--parchment-dim)",
            lineHeight: 1.55,
            marginBottom: "0.5rem",
          }}
        >
          ACKNOWLEDGE marks the contradiction as standing — it stays
          visible and continues to be eligible for source-driven
          resolution. DISPUTE is terminal: the engine got it wrong;
          the dispute feeds calibration review.
        </p>
        <EngineActions contradictionId={row.id} status={row.status} />
      </section>
    </main>
  );
}

function PrincipleCard({
  label,
  principleId,
  text,
  supported,
}: {
  label: string;
  principleId: string;
  text: string;
  supported: boolean;
}) {
  return (
    <div
      className="portal-card"
      style={{
        padding: "1rem 1.25rem",
        marginBottom: "0.5rem",
        borderLeft: supported
          ? "3px solid var(--gold)"
          : "3px solid var(--stone-mid)",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: "0.6rem",
          alignItems: "baseline",
          marginBottom: "0.25rem",
        }}
      >
        <span
          className="mono"
          style={{
            fontSize: "0.65rem",
            color: "var(--amber-dim)",
            letterSpacing: "0.12em",
          }}
        >
          Principle {label}
        </span>
        {supported ? (
          <span
            className="mono"
            style={{
              fontSize: "0.55rem",
              color: "var(--gold)",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
            }}
          >
            Supported by current evidence
          </span>
        ) : null}
      </div>
      <p
        style={{
          margin: 0,
          fontFamily: "'EB Garamond', serif",
          fontSize: "0.95rem",
          color: "var(--parchment)",
          lineHeight: 1.55,
        }}
      >
        {text}
      </p>
      <Link
        href={`/conclusions/${principleId}`}
        style={{
          fontSize: "0.65rem",
          color: "var(--gold)",
          textDecoration: "none",
        }}
      >
        View conclusion →
      </Link>
    </div>
  );
}

function LifecycleEventRow({ ev }: { ev: LifecycleEvent }) {
  const after = ev.status_after ?? "?";
  const color = STATUS_COLOR[after] ?? "var(--parchment)";
  const sources = ev.triggering_source_ids ?? [];
  const score = ev.score_change ?? null;
  return (
    <li
      style={{
        padding: "0.65rem 0.85rem",
        border: "1px solid var(--stone-mid)",
        borderLeft: `2px solid ${color}`,
        borderRadius: 2,
      }}
    >
      <div
        style={{
          display: "flex",
          gap: "0.6rem",
          alignItems: "baseline",
          flexWrap: "wrap",
        }}
      >
        <span
          className="mono"
          style={{
            fontSize: "0.6rem",
            color: "var(--parchment-dim)",
            letterSpacing: "0.1em",
          }}
        >
          {new Date(ev.at).toLocaleString()}
        </span>
        <span
          className="mono"
          style={{
            fontSize: "0.65rem",
            color,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
          }}
        >
          {ev.status_before ? `${ev.status_before} → ${after}` : after}
        </span>
      </div>
      {ev.rationale ? (
        <p
          style={{
            margin: "0.4rem 0 0",
            fontFamily: "'EB Garamond', serif",
            fontSize: "0.9rem",
            color: "var(--parchment)",
            lineHeight: 1.5,
          }}
        >
          {ev.rationale}
        </p>
      ) : null}
      {sources.length > 0 ? (
        <div
          className="mono"
          style={{
            marginTop: "0.4rem",
            fontSize: "0.6rem",
            color: "var(--parchment-dim)",
            letterSpacing: "0.08em",
          }}
        >
          source: {sources.join(", ")}
        </div>
      ) : null}
      {score ? (
        <div
          className="mono"
          style={{
            marginTop: "0.2rem",
            fontSize: "0.6rem",
            color: "var(--parchment-dim)",
            letterSpacing: "0.08em",
          }}
        >
          {Object.entries(score)
            .map(([k, v]) => `${k}=${typeof v === "number" ? v.toFixed(2) : v}`)
            .join(" · ")}
        </div>
      ) : null}
    </li>
  );
}
