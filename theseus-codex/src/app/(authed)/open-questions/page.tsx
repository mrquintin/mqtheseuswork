import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import SculptureBackdrop from "@/components/SculptureBackdrop";
import { getFounder } from "@/lib/auth";
import {
  listOpenQuestionDomains,
  loadTriageQueue,
  promoteOpenQuestionToResearch,
  type TriageRow,
} from "@/lib/openQuestionsApi";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Open questions — founder triage queue.
 *
 * Previously a simple chronological list of unresolved coherence pairs.
 * Now a triage queue: priority-sorted (centrality + replayability +
 * calibration relevance, all bounded so no single signal dominates),
 * filterable by domain, with a "promote to research" action that writes
 * a `ResearchSuggestion` and removes the question from the active queue
 * the next render.
 *
 * The Discobolus header still carries the page's visual weight; the
 * cards are typography-first so the eye reads the question summary,
 * the priority bar, and the actionable buttons in that order.
 */

export const dynamic = "force-dynamic";

type SearchParams = { domain?: string };

function priorityBar(score: number): string {
  const cells = 12;
  const filled = Math.round(Math.max(0, Math.min(1, score)) * cells);
  return "█".repeat(filled) + "░".repeat(cells - filled);
}

function priorityColor(score: number): string {
  if (score >= 0.7) return "var(--ember, #c0392b)";
  if (score >= 0.45) return "var(--amber, #d4a017)";
  return "var(--parchment-dim)";
}

export default async function OpenQuestionsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const { domain } = (await searchParams) ?? {};
  const [rows, allDomains] = await Promise.all([
    loadTriageQueue(tenant.organizationId, { domain }),
    listOpenQuestionDomains(tenant.organizationId),
  ]);

  async function promote(formData: FormData) {
    "use server";
    const founder = await getFounder();
    if (!founder) redirect("/login");
    const id = String(formData.get("questionId") ?? "");
    if (!id) return;
    await promoteOpenQuestionToResearch(
      founder.organizationId,
      id,
      founder.id,
    );
    revalidatePath("/open-questions");
  }

  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <SculptureBackdrop
        src="/sculptures/discobolus.mesh.bin"
        side="left"
        yawSpeed={0.022}
      />

      <main
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: "1080px",
          margin: "0 auto",
          padding: "2.75rem 2rem",
        }}
      >
        <header style={{ marginBottom: "2rem" }}>
          <h1
            style={{
              fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
              fontSize: "2rem",
              letterSpacing: "0.18em",
              color: "var(--amber)",
              textShadow: "var(--glow-md)",
              margin: 0,
            }}
          >
            Quaestiones Apertae
          </h1>
          <p
            className="mono"
            style={{
              fontSize: "0.65rem",
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              marginTop: "0.25rem",
            }}
          >
            Triage queue · priority-sorted · {rows.length} active
          </p>
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              fontStyle: "italic",
              fontSize: "1rem",
              color: "var(--parchment-dim)",
              marginTop: "0.75rem",
              lineHeight: 1.55,
              maxWidth: "44em",
            }}
          >
            Each question gets a bounded priority from three signals —
            centrality (downstream conclusions affected), replayability
            (cost to resolve), and calibration relevance (thinness of
            track record in the question&apos;s domain). Centrality alone
            cannot run away with the score; a niche-but-cheap question
            in a thin-calibration domain can still rank near the top.
          </p>
        </header>

        <DomainFilter active={domain ?? ""} options={allDomains} />

        {rows.length === 0 ? (
          <div
            className="ascii-frame"
            data-label="LIMEN · THRESHOLD"
            style={{ padding: "2.5rem 1rem", textAlign: "center", marginTop: "1.5rem" }}
          >
            <p
              style={{
                fontFamily: "'EB Garamond', serif",
                fontStyle: "italic",
                fontSize: "1.15rem",
                color: "var(--parchment)",
                margin: 0,
              }}
            >
              Nullus limen patens.
            </p>
            <p
              className="mono"
              style={{
                fontSize: "0.7rem",
                color: "var(--parchment-dim)",
                marginTop: "0.4rem",
              }}
            >
              {domain
                ? `No active questions in domain "${domain}".`
                : "No open questions awaiting triage."}
            </p>
          </div>
        ) : (
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              marginTop: "1.5rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.9rem",
            }}
          >
            {rows.map((row) => (
              <TriageCard key={row.id} row={row} promote={promote} />
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}

function DomainFilter({
  active,
  options,
}: {
  active: string;
  options: string[];
}) {
  if (options.length === 0) return null;
  const chipBase: React.CSSProperties = {
    fontSize: "0.6rem",
    letterSpacing: "0.18em",
    textTransform: "uppercase",
    padding: "0.35rem 0.75rem",
    border: "1px solid var(--border)",
    color: "var(--parchment-dim)",
    textDecoration: "none",
  };
  const chipActive: React.CSSProperties = {
    ...chipBase,
    color: "var(--amber)",
    borderColor: "var(--amber)",
  };
  return (
    <div
      className="mono"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.4rem",
        alignItems: "center",
      }}
    >
      <span style={{ fontSize: "0.6rem", color: "var(--parchment-dim)" }}>
        DOMAIN:
      </span>
      <a href="/open-questions" style={active === "" ? chipActive : chipBase}>
        all
      </a>
      {options.map((d) => (
        <a
          key={d}
          href={`/open-questions?domain=${encodeURIComponent(d)}`}
          style={active === d ? chipActive : chipBase}
        >
          {d}
        </a>
      ))}
    </div>
  );
}

function TriageCard({
  row,
  promote,
}: {
  row: TriageRow;
  promote: (formData: FormData) => Promise<void>;
}) {
  const tensionCount = (row.layerDisagreementSummary.match(/\bvs\b/gi) || []).length;
  return (
    <li
      className="portal-card"
      style={{
        padding: "1.1rem 1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.6rem",
      }}
    >
      <div
        className="mono"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "0.6rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
        }}
      >
        <span style={{ color: priorityColor(row.priority.score) }}>
          Priority · {row.priority.score.toFixed(2)} · {priorityBar(row.priority.score)}
        </span>
        <span style={{ color: "var(--parchment-dim)" }}>
          {row.domain || "domain unknown"} · {row.linkedConclusionCount} linked
        </span>
      </div>

      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontSize: "1.05rem",
          color: "var(--parchment)",
          margin: 0,
          lineHeight: 1.55,
        }}
      >
        {row.summary}
      </p>

      {row.unresolvedReason && (
        <p
          style={{
            fontSize: "0.8rem",
            color: "var(--parchment-dim)",
            margin: 0,
            lineHeight: 1.5,
          }}
        >
          {row.unresolvedReason}
        </p>
      )}

      <PriorityBreakdown row={row} tensionCount={tensionCount} />

      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap",
          marginTop: "0.25rem",
        }}
      >
        <form action={promote}>
          <input type="hidden" name="questionId" value={row.id} />
          <button
            type="submit"
            className="btn-solid btn"
            style={{ fontSize: "0.65rem" }}
          >
            Promote to research →
          </button>
        </form>
        <a
          href={`/conclusions/${row.claimAId}`}
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Claim A
        </a>
        <a
          href={`/conclusions/${row.claimBId}`}
          className="btn"
          style={{ fontSize: "0.65rem", textDecoration: "none" }}
        >
          Claim B
        </a>
      </div>
    </li>
  );
}

function PriorityBreakdown({
  row,
  tensionCount,
}: {
  row: TriageRow;
  tensionCount: number;
}) {
  return (
    <div
      className="mono"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: "0.4rem",
        fontSize: "0.6rem",
        color: "var(--parchment-dim)",
        letterSpacing: "0.08em",
      }}
    >
      {row.priority.components.map((c) => (
        <div key={c.name}>
          <span style={{ textTransform: "uppercase" }}>
            {c.name.replace(/_/g, " ")}:
          </span>{" "}
          <span style={{ color: "var(--parchment)" }}>
            {c.raw.toFixed(2)}
          </span>
          <span> × {c.weight.toFixed(2)}</span>
        </div>
      ))}
      <div>
        <span style={{ textTransform: "uppercase" }}>layers disagreeing:</span>{" "}
        <span style={{ color: "var(--parchment)" }}>{tensionCount || "—"}</span>
      </div>
    </div>
  );
}
