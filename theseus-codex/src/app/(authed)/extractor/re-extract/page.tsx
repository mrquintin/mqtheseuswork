import Link from "next/link";
import { redirect } from "next/navigation";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

/**
 * Extraction audit log (decommissioned triage surface, 2026-05-17).
 *
 * The page used to gate principle-shaped rewrites of legacy first-person
 * conclusions behind founder accept/edit/reject. After auto-accept on
 * extraction (`auto_accept_principles_2026_05_17`), no manual triage is
 * required: the surface remains as a READ-ONLY audit of what the agent
 * did, with no actionable buttons.
 *
 * Rendering: the most recent first-person conclusions side-by-side with
 * any agent rewrite captured in the rationale column. The founder can
 * still inspect; they no longer gate.
 */

// Regex mirrors `is_first_person_conclusion` in
// noosphere/noosphere/conclusions.py.
const FIRST_PERSON_LEADING =
  /^\s*["'“‘]?(i|i['’]\w*|i'd|i'm|i've|we|we['’]\w*|we're|we've|my|our)\b/i;

function isFirstPerson(text: string | null | undefined): boolean {
  if (!text) return false;
  return FIRST_PERSON_LEADING.test(text);
}

type AuditRow = {
  id: string;
  originalText: string;
  rewrittenText: string;
  sourceSpan: string;
  createdAt: string;
};

export default async function ExtractionAuditLogPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const rows = await db.conclusion.findMany({
    where: { organizationId: tenant.organizationId },
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

  const auditRows: AuditRow[] = rows
    .filter((r) => isFirstPerson(r.text) || isFirstPerson(r.rationale))
    .map((r) => ({
      id: r.id,
      originalText: isFirstPerson(r.rationale) ? (r.rationale ?? "") : r.text,
      rewrittenText: isFirstPerson(r.rationale) ? r.text : "",
      sourceSpan: r.sourceSpan ?? "",
      createdAt: r.createdAt.toISOString(),
    }));

  return (
    <main
      data-testid="extraction-audit-log"
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
          Extraction audit log
        </h1>
        <p
          className="mono"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--parchment-dim)",
            marginTop: "0.4rem",
          }}
          data-testid="audit-log-banner"
        >
          Principle extraction is automatic. This page is a historical
          audit log.
        </p>
        <p style={{ opacity: 0.65, marginTop: "0.5rem", maxWidth: "44em" }}>
          Legacy first-person conclusions and any principle-shaped
          rewrite the extractor produced for them. Read-only — no founder
          action is required for principles to publish.
        </p>
        <p style={{ opacity: 0.55, marginTop: "0.25rem", fontSize: "0.85rem" }}>
          {auditRows.length} row{auditRows.length === 1 ? "" : "s"} in window
        </p>
      </header>

      {auditRows.length === 0 ? (
        <p style={{ opacity: 0.7 }}>
          No first-person conclusions in the recent window. The extractor
          is producing principle-shaped output and the legacy corpus is
          clean.
        </p>
      ) : (
        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {auditRows.map((row) => (
            <li
              key={row.id}
              style={{
                border: "1px solid var(--line, #2a2a2a)",
                borderRadius: "0.5rem",
                padding: "1rem 1.25rem",
                marginBottom: "1rem",
              }}
            >
              <header
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: "0.75rem",
                  opacity: 0.65,
                  marginBottom: "0.5rem",
                }}
              >
                <Link
                  href={`/conclusions/${row.id}`}
                  style={{ color: "inherit", textDecoration: "none" }}
                >
                  conclusion · {row.id.slice(0, 8)}
                </Link>
                <span>{new Date(row.createdAt).toLocaleDateString()}</span>
              </header>

              {row.sourceSpan ? (
                <section style={{ marginBottom: "0.65rem" }}>
                  <h3
                    style={{
                      fontSize: "0.8rem",
                      opacity: 0.7,
                      margin: "0 0 0.25rem",
                    }}
                  >
                    source span
                  </h3>
                  <blockquote
                    style={{
                      fontFamily: "monospace",
                      fontSize: "0.85rem",
                      margin: 0,
                      padding: "0.5rem 0.75rem",
                      borderLeft: "3px solid var(--amber, #c98c1a)",
                      background: "rgba(255,255,255,0.02)",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {row.sourceSpan}
                  </blockquote>
                </section>
              ) : null}

              <section style={{ marginBottom: "0.65rem" }}>
                <h3
                  style={{ fontSize: "0.8rem", opacity: 0.7, margin: "0 0 0.25rem" }}
                >
                  original (first-person)
                </h3>
                <p style={{ margin: 0, fontStyle: "italic" }}>{row.originalText}</p>
              </section>

              {row.rewrittenText ? (
                <section>
                  <h3
                    style={{
                      fontSize: "0.8rem",
                      opacity: 0.7,
                      margin: "0 0 0.25rem",
                    }}
                  >
                    rewritten (principle-shaped)
                  </h3>
                  <p style={{ margin: 0 }}>{row.rewrittenText}</p>
                </section>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
