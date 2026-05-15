import { notFound, redirect } from "next/navigation";

import MemoDrafter from "@/components/deals/MemoDrafter";
import PrincipleAlignmentTable, {
  type AlignmentRow,
} from "@/components/deals/PrincipleAlignmentTable";
import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

export const dynamic = "force-dynamic";

type SourceDoc = { label: string; uri: string; kind?: string };

type DealNoteView = {
  id: string;
  body: string;
  authorFounderId: string;
  citedPrincipleIds: string[];
  createdAt: string;
};

/**
 * /deals/[id] — single deal detail.
 *
 * Sections:
 *   1. Header — name, stage, sector, geo, decision status.
 *   2. Source documents — uploaded manifest.
 *   3. Principle-alignment table — per-principle verdict + citations.
 *   4. Memo drafter — generates a DRAFT memo from the alignment table.
 *      The draft is never auto-promoted; the partner edits + signs.
 *   5. Partner notes — append-only log, each note auto-links cited
 *      principle ids.
 */
export default async function DealDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const { id } = await params;

  const deal = await db.deal.findFirst({
    where: { id, organizationId: tenant.organizationId },
    include: {
      alignments: { orderBy: { confidence: "desc" } },
      notes: { orderBy: { createdAt: "desc" } },
    },
  });
  if (!deal) notFound();

  let sourceDocs: SourceDoc[] = [];
  try {
    const parsed = JSON.parse(deal.sourceDocumentsJson || "[]");
    if (Array.isArray(parsed)) {
      sourceDocs = parsed.filter(
        (d): d is SourceDoc =>
          d && typeof d.label === "string" && typeof d.uri === "string",
      );
    }
  } catch {
    sourceDocs = [];
  }

  // Hydrate the principle text for each alignment row in one query so
  // the table can render the principle's canonical statement without
  // a per-row fetch.
  const principleIds = Array.from(
    new Set(deal.alignments.map((a) => a.principleId)),
  );
  const principles = principleIds.length
    ? await db.principle.findMany({
        where: {
          id: { in: principleIds },
          organizationId: tenant.organizationId,
        },
      })
    : [];
  const principleById = new Map(principles.map((p) => [p.id, p]));

  const alignmentRows: AlignmentRow[] = deal.alignments.map((a) => {
    let citations: Array<{
      quote: string;
      source_uri?: string;
      conclusion_id?: string;
      locator?: string;
    }> = [];
    try {
      const parsed = JSON.parse(a.citationsJson || "[]");
      if (Array.isArray(parsed)) citations = parsed;
    } catch {
      citations = [];
    }
    const p = principleById.get(a.principleId);
    let domains: string[] = [];
    if (p) {
      try {
        const parsed = JSON.parse(p.domainsJson || "[]");
        if (Array.isArray(parsed)) {
          domains = parsed.filter((d): d is string => typeof d === "string");
        }
      } catch {
        domains = [];
      }
    }
    return {
      principleId: a.principleId,
      principleText: p?.text ?? "(principle no longer in tenant)",
      principleDomains: domains,
      verdict: a.verdict,
      rationale: a.rationale,
      confidence: a.confidence,
      citations,
    };
  });

  const notes: DealNoteView[] = deal.notes.map((n) => {
    let cited: string[] = [];
    try {
      const parsed = JSON.parse(n.citedPrincipleIdsJson || "[]");
      if (Array.isArray(parsed))
        cited = parsed.filter((x): x is string => typeof x === "string");
    } catch {
      cited = [];
    }
    return {
      id: n.id,
      body: n.body,
      authorFounderId: n.authorFounderId,
      citedPrincipleIds: cited,
      createdAt: n.createdAt.toISOString(),
    };
  });

  return (
    <main
      style={{
        maxWidth: "1080px",
        margin: "0 auto",
        padding: "2.75rem 2rem",
      }}
    >
      <header style={{ marginBottom: "1.75rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--amber)",
            letterSpacing: "0.08em",
            margin: 0,
          }}
        >
          {deal.name}
        </h1>
        <p
          className="mono"
          style={{
            fontSize: "0.7rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginTop: "0.45rem",
          }}
        >
          {[deal.stage, deal.sector, deal.geo, deal.decisionStatus]
            .filter(Boolean)
            .join(" · ")}
        </p>
        {deal.description ? (
          <p
            style={{
              fontFamily: "'EB Garamond', serif",
              color: "var(--parchment)",
              marginTop: "0.9rem",
              lineHeight: 1.55,
              maxWidth: "44em",
            }}
          >
            {deal.description}
          </p>
        ) : null}
      </header>

      <section style={{ marginBottom: "2rem" }}>
        <h2 style={sectionHeading}>Source documents</h2>
        {sourceDocs.length === 0 ? (
          <p style={emptyNote} data-testid="deal-source-empty">
            No source documents uploaded yet.
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {sourceDocs.map((doc, i) => (
              <li
                key={`${doc.uri}-${i}`}
                style={{
                  padding: "0.4rem 0",
                  borderBottom: "1px solid rgba(180,150,80,0.12)",
                  fontFamily: "'EB Garamond', serif",
                }}
              >
                <a
                  href={doc.uri}
                  style={{ color: "var(--amber)" }}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  {doc.label}
                </a>
                {doc.kind ? (
                  <span
                    className="mono"
                    style={{
                      marginLeft: "0.6rem",
                      fontSize: "0.65rem",
                      letterSpacing: "0.16em",
                      color: "var(--parchment-dim)",
                    }}
                  >
                    {doc.kind.toUpperCase()}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginBottom: "2rem" }}>
        <h2 style={sectionHeading}>Principle alignment</h2>
        <PrincipleAlignmentTable rows={alignmentRows} dealId={deal.id} />
      </section>

      <section style={{ marginBottom: "2rem" }}>
        <h2 style={sectionHeading}>Sketch a memo</h2>
        <MemoDrafter
          dealId={deal.id}
          dealName={deal.name}
          existingDraft={deal.memoDraft}
          existingFinal={deal.memoFinal}
          alignment={alignmentRows}
        />
      </section>

      <section>
        <h2 style={sectionHeading}>Partner notes</h2>
        {notes.length === 0 ? (
          <p style={emptyNote}>No notes yet.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {notes.map((n) => (
              <li
                key={n.id}
                style={{
                  padding: "0.7rem 0",
                  borderBottom: "1px solid rgba(180,150,80,0.12)",
                  fontFamily: "'EB Garamond', serif",
                  whiteSpace: "pre-wrap",
                }}
              >
                <div
                  className="mono"
                  style={{
                    fontSize: "0.65rem",
                    letterSpacing: "0.16em",
                    textTransform: "uppercase",
                    color: "var(--parchment-dim)",
                    marginBottom: "0.25rem",
                  }}
                >
                  {n.createdAt.slice(0, 16).replace("T", " ")}
                </div>
                <div>{n.body}</div>
                {n.citedPrincipleIds.length ? (
                  <div
                    className="mono"
                    style={{
                      marginTop: "0.4rem",
                      fontSize: "0.65rem",
                      letterSpacing: "0.16em",
                      color: "var(--amber-dim)",
                    }}
                  >
                    cites:{" "}
                    {n.citedPrincipleIds.map((pid, i) => (
                      <span key={pid}>
                        {i > 0 ? ", " : null}
                        <a
                          href={`/principles/${pid}`}
                          style={{ color: "var(--amber)" }}
                        >
                          {pid.slice(0, 8)}
                        </a>
                      </span>
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

const sectionHeading: React.CSSProperties = {
  fontFamily: "'Cinzel', serif",
  color: "var(--amber)",
  letterSpacing: "0.12em",
  fontSize: "0.95rem",
  textTransform: "uppercase",
  margin: "0 0 0.8rem 0",
};

const emptyNote: React.CSSProperties = {
  fontFamily: "'EB Garamond', serif",
  fontStyle: "italic",
  color: "var(--parchment-dim)",
  margin: 0,
};
