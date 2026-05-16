/**
 * /library/triage — one-time founder triage for prompt-09 provenance.
 *
 * The migration backfills every existing Upload to provenance=PROPRIETARY.
 * Some of those rows are actually external — articles, references,
 * pieces the firm reads but didn't write. The founder reviews this
 * list once and re-tags any that should be ENDORSED / STUDIED /
 * OPPOSING. After triage, new uploads pick their provenance up front
 * via the upload form and rarely come back here.
 *
 * The page deliberately lists every PROPRIETARY-tagged row (not just
 * "old" ones). There's no automated signal for "this is mis-tagged" —
 * only the founder can tell, so we surface them all and let the
 * founder decide.
 */
import { redirect } from "next/navigation";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";
import { canWrite } from "@/lib/roles";

import { retagAction } from "./actions";

export const dynamic = "force-dynamic";

const KIND_OPTIONS = [
  { value: "PROPRIETARY", label: "Proprietary (keep)" },
  { value: "ENDORSED_EXTERNAL", label: "Endorsed external" },
  { value: "STUDIED_EXTERNAL", label: "Studied external" },
  { value: "OPPOSING_EXTERNAL", label: "Opposing external" },
] as const;

export default async function TriagePage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  if (!canWrite(tenant.role)) {
    redirect("/library");
  }

  const [proprietaryCount, totalCount, rows] = await Promise.all([
    db.upload.count({
      where: {
        organizationId: tenant.organizationId,
        deletedAt: null,
        provenance: "PROPRIETARY",
      },
    }),
    db.upload.count({
      where: { organizationId: tenant.organizationId, deletedAt: null },
    }),
    db.upload.findMany({
      where: {
        organizationId: tenant.organizationId,
        deletedAt: null,
        provenance: "PROPRIETARY",
      },
      select: {
        id: true,
        title: true,
        originalName: true,
        sourceType: true,
        createdAt: true,
        provenance: true,
      },
      orderBy: { createdAt: "desc" },
      take: 200,
    }),
  ]);

  return (
    <main
      style={{
        maxWidth: "880px",
        margin: "0 auto",
        padding: "3rem 1.5rem 5rem",
      }}
    >
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          letterSpacing: "0.06em",
          color: "var(--amber)",
          textShadow: "var(--glow-sm)",
          fontSize: "1.6rem",
          margin: 0,
        }}
      >
        Library triage
      </h1>
      <p
        style={{
          color: "var(--parchment-dim)",
          marginTop: "0.8rem",
          lineHeight: 1.65,
        }}
      >
        Every artifact uploaded before provenance demarcation defaulted
        to <strong>PROPRIETARY</strong>. {proprietaryCount} of{" "}
        {totalCount} rows currently carry that tag. Review the list and
        retag any that the firm did not author. External choices need a
        short rationale (≥ 30 chars) — &ldquo;why is this in our
        library?&rdquo;
      </p>

      {rows.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)", marginTop: "2rem" }}>
          No PROPRIETARY-tagged uploads to review.
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, marginTop: "2rem" }}>
          {rows.map((row) => (
            <li
              key={row.id}
              style={{
                padding: "1rem 0",
                borderBottom: "1px solid var(--stroke)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "1rem",
                  marginBottom: "0.5rem",
                }}
              >
                <strong style={{ color: "var(--parchment)" }}>
                  {row.title || row.originalName}
                </strong>
                <span
                  className="mono"
                  style={{
                    fontSize: "0.6rem",
                    letterSpacing: "0.12em",
                    color: "var(--parchment-dim)",
                  }}
                >
                  {new Date(row.createdAt).toISOString().slice(0, 10)} ·{" "}
                  {row.sourceType}
                </span>
              </div>
              <form
                action={retagAction}
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "0.6rem",
                  alignItems: "center",
                }}
              >
                <input type="hidden" name="uploadId" value={row.id} />
                <select
                  name="provenance"
                  defaultValue="PROPRIETARY"
                  style={{
                    padding: "0.4rem 0.6rem",
                    background: "rgba(0,0,0,0.25)",
                    color: "var(--parchment)",
                    border: "1px solid var(--stroke)",
                    borderRadius: "3px",
                  }}
                >
                  {KIND_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <input
                  type="text"
                  name="rationale"
                  placeholder="Rationale (required for external)"
                  style={{
                    flex: "1 1 18rem",
                    padding: "0.4rem 0.6rem",
                    background: "rgba(0,0,0,0.25)",
                    color: "var(--parchment)",
                    border: "1px solid var(--stroke)",
                    borderRadius: "3px",
                  }}
                />
                <button
                  type="submit"
                  style={{
                    padding: "0.45rem 0.9rem",
                    border: "1px solid var(--amber)",
                    background: "transparent",
                    color: "var(--amber)",
                    fontFamily: "inherit",
                    cursor: "pointer",
                    borderRadius: "3px",
                  }}
                >
                  Retag
                </button>
              </form>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
