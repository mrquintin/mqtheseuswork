import { Prisma } from "@prisma/client";
import { db } from "@/lib/db";

type Row = {
  id: string;
  conclusionId: string;
  tradition: string;
  objectionText: string;
  status: string;
  finalVerdict: string;
  stale: boolean;
};

type AdvRow = {
  id: string;
  conclusion_id: string;
  payload_json: string;
};

function badge(status: string, stale: boolean) {
  if (stale) return "stale";
  if (status === "survived" || status === "addressed") return "surviving";
  if (status === "fallen" || status === "fatal") return "fallen";
  return status;
}

export default async function AdversarialPage() {
  let rows: AdvRow[] = [];
  try {
    rows = await db.$queryRaw<AdvRow[]>(Prisma.sql`
      SELECT id, conclusion_id, payload_json
      FROM adversarial_challenge
      ORDER BY created_at DESC
      LIMIT 120
    `);
  } catch {
    rows = [];
  }

  const items: Row[] = rows.map((r) => {
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(r.payload_json) as Record<string, unknown>;
    } catch {
      /* empty */
    }
    const status = (payload.status as string) || "pending";
    const staleRaw = payload.stale_after ?? payload.staleAfter;
    const stale =
      staleRaw != null &&
      typeof staleRaw === "string" &&
      new Date(staleRaw as string).getTime() < Date.now();
    return {
      id: r.id,
      conclusionId: r.conclusion_id,
      tradition: (payload.tradition as string) || "",
      objectionText: (payload.objection_text as string) || "",
      status,
      finalVerdict: (payload.final_verdict as string) || "",
      stale,
    };
  });

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Adversarial coherence
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
        Strongest objections generated for firm conclusions. Badges reflect evaluation status. Use{" "}
        <code style={{ color: "var(--gold-dim)" }}>POST /api/adversarial/[id]/override</code> to record human
        overrides.
      </p>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "1rem" }}>
        {items.length === 0 ? (
          <li className="portal-card" style={{ padding: "1rem 1.25rem", color: "var(--parchment-dim)" }}>
            No challenges in this database yet, or the <code>adversarial_challenge</code> table does not exist. Run{" "}
            <code style={{ color: "var(--gold-dim)" }}>python -m noosphere adversarial --conclusion …</code> against
            the same SQLite file as the portal, then refresh.
          </li>
        ) : (
          items.map((c) => (
            <li key={c.id} className="portal-card" style={{ padding: "1rem 1.25rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                <span style={{ fontSize: "0.65rem", color: "var(--gold-dim)", textTransform: "uppercase" }}>
                  conclusion {c.conclusionId.slice(0, 8)}…
                </span>
                <span
                  style={{
                    fontSize: "0.65rem",
                    letterSpacing: "0.1em",
                    color:
                      badge(c.status, c.stale) === "fallen" ? "var(--danger, #c44)" : "var(--parchment)",
                  }}
                >
                  {badge(c.status, c.stale)}
                </span>
              </div>
              <div style={{ marginTop: "0.35rem", fontSize: "0.75rem", color: "var(--gold-dim)" }}>{c.tradition}</div>
              <p style={{ marginTop: "0.5rem", color: "var(--parchment)" }}>{c.objectionText}</p>
              {c.finalVerdict ? (
                <p style={{ marginTop: "0.35rem", fontSize: "0.8rem", color: "var(--parchment-dim)" }}>
                  Verdict: {c.finalVerdict}
                </p>
              ) : null}
            </li>
          ))
        )}
      </ul>
    </main>
  );
}
