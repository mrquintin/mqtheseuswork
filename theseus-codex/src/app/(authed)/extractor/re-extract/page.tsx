import { redirect } from "next/navigation";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

import ReExtractClient, { type ReExtractRow } from "./ReExtractClient";

export const dynamic = "force-dynamic";

/**
 * Founder-confirmable re-extraction queue (prompt 56, 2026-05-13).
 *
 * The principle-shape contract introduced by the rewritten
 * `PrincipleExtractor` does NOT auto-rewrite legacy `Conclusion` rows
 * that already shipped to the firm corpus. Instead, every conclusion
 * whose surface form opens with a first-person pronoun (I / we / my /
 * our) appears here, paired with:
 *
 *   - the verbatim source span the LLM lifted it from,
 *   - the existing first-person text we wrote,
 *   - the agent's proposed third-person, principle-shaped rewrite.
 *
 * The founder accepts, edits-then-accepts, or rejects per row. No
 * database write happens without an explicit founder action — the
 * agent's recommendation is advisory.
 *
 * The re-extracted text and structured fields land in the existing
 * `Conclusion` columns introduced by
 * `20260513150000_principle_fields/migration.sql`. The row's original
 * source-spans are preserved verbatim — see the contract in
 * `noosphere/noosphere/extractors/_prompts/principle_extraction_system.md`.
 */

// Regex mirrors `is_first_person_conclusion` in
// noosphere/noosphere/conclusions.py. Kept in sync intentionally — the
// Python side flags rows for an offline backfill pass; this TS side
// filters the queue rendered to the founder.
const FIRST_PERSON_LEADING =
  /^\s*["'“‘]?(i|i['’]\w*|i'd|i'm|i've|we|we['’]\w*|we're|we've|my|our)\b/i;

function isFirstPerson(text: string | null | undefined): boolean {
  if (!text) return false;
  return FIRST_PERSON_LEADING.test(text);
}

export default async function ReExtractQueuePage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const rows = await db.conclusion.findMany({
    where: {
      organizationId: tenant.organizationId,
      principleKind: null,
    },
    select: {
      id: true,
      text: true,
      sourceSpan: true,
      rationale: true,
      createdAt: true,
    },
    orderBy: { createdAt: "desc" },
    take: 200,
  });

  const queue: ReExtractRow[] = rows
    .filter((r) => isFirstPerson(r.text))
    .map((r) => ({
      id: r.id,
      currentText: r.text,
      sourceSpan: r.sourceSpan ?? "",
      // The agent's proposed rewrite is filled in later by the
      // offline `noosphere extractor reextract` job and stored under
      // the rationale column until the founder confirms. Surfacing
      // whatever is there today keeps the queue actionable; an empty
      // proposal still lets the founder edit-then-accept manually.
      proposedText: r.rationale && !isFirstPerson(r.rationale) ? r.rationale : "",
      createdAt: r.createdAt.toISOString(),
    }));

  return (
    <main
      style={{
        maxWidth: "1080px",
        margin: "0 auto",
        padding: "2.75rem 2rem",
      }}
    >
      <header style={{ marginBottom: "1.5rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.12em",
            margin: 0,
          }}
        >
          Extractor · re-extract queue
        </h1>
        <p style={{ opacity: 0.75, marginTop: "0.5rem" }}>
          Legacy conclusions written in first-person voice. The agent
          proposes a principle-shaped rewrite; you accept, edit, or
          reject per row. Nothing publishes without your action.
        </p>
        <p style={{ opacity: 0.6, marginTop: "0.25rem", fontSize: "0.85rem" }}>
          {queue.length} row{queue.length === 1 ? "" : "s"} pending review
        </p>
      </header>
      <ReExtractClient rows={queue} />
    </main>
  );
}
