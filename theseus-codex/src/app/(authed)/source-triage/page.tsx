import { redirect } from "next/navigation";
import { db } from "@/lib/db";
import { getFounder } from "@/lib/auth";
import { verdictPill, type CitationVerdictLabel } from "@/lib/citationVerdict";

export const dynamic = "force-dynamic";

const STATUS_PILL: Record<string, { bg: string; fg: string; label: string }> = {
  RETRACTED: { bg: "#5b1414", fg: "#ffd1d1", label: "retracted" },
  CORRECTED: { bg: "#5b3414", fg: "#ffe2c2", label: "corrected" },
  EXPIRED: { bg: "#3a3a3a", fg: "#dcdcdc", label: "expired" },
  DISPUTED: { bg: "#5a4a14", fg: "#ffe9a8", label: "disputed" },
};

function pillStyle(status: string) {
  return STATUS_PILL[status] ?? { bg: "#222", fg: "#ddd", label: status.toLowerCase() };
}

export default async function SourceTriagePage() {
  const founder = await getFounder();
  if (!founder) redirect("/login");

  const items = await db.sourceTriageItem.findMany({
    where: {
      organizationId: founder.organizationId,
      decision: "pending",
    },
    orderBy: { createdAt: "desc" },
    take: 100,
  });

  const conclusionIds = Array.from(new Set(items.map((i) => i.conclusionId)));
  const conclusions = conclusionIds.length
    ? await db.conclusion.findMany({
        where: { id: { in: conclusionIds }, organizationId: founder.organizationId },
        select: { id: true, text: true, confidenceTier: true },
      })
    : [];
  const conclusionMap = new Map(conclusions.map((c) => [c.id, c]));

  const standingIds = Array.from(
    new Set(items.map((i) => i.standingId).filter((id): id is string => Boolean(id))),
  );
  const standings = standingIds.length
    ? await db.sourceStanding.findMany({
        where: { id: { in: standingIds }, organizationId: founder.organizationId },
        select: {
          id: true,
          reason: true,
          poller: true,
          observedAt: true,
          noticeSourceId: true,
        },
      })
    : [];
  const standingMap = new Map(standings.map((s) => [s.id, s]));

  const verdictIds = Array.from(
    new Set(items.map((i) => i.verdictId).filter((id): id is string => Boolean(id))),
  );
  const verdicts = verdictIds.length
    ? await db.citationVerdict.findMany({
        where: { id: { in: verdictIds }, organizationId: founder.organizationId },
        select: {
          id: true,
          relation: true,
          relationHolds: true,
          confidence: true,
          excerptUsed: true,
          statedClaim: true,
          modelVersion: true,
          cascadeWeight: true,
          citationKind: true,
          citationId: true,
        },
      })
    : [];
  const verdictMap = new Map(verdicts.map((v) => [v.id, v]));

  const standingItems = items.filter((i) => i.trigger !== "citation_verdict");
  const verdictItems = items.filter((i) => i.trigger === "citation_verdict");

  return (
    <main style={{ maxWidth: "960px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
        }}
      >
        Source triage
      </h1>
      <p style={{ color: "var(--parchment-dim)", marginBottom: "1.5rem" }}>
        Sources cited by firm conclusions whose standing has changed, or whose
        cited text the citation-chain validator could not square with the
        firm&apos;s stated claim. Confirm to drop the cite, or override with a
        stated reason.
      </p>

      {items.length === 0 ? (
        <p style={{ color: "var(--parchment-dim)" }}>No pending source-triage items.</p>
      ) : null}

      {standingItems.length > 0 ? (
        <section data-testid="standing-triage-section">
          <h2
            style={{
              color: "var(--parchment)",
              fontFamily: "'Cinzel', serif",
              fontSize: "1rem",
              letterSpacing: "0.08em",
              marginTop: "1.5rem",
              textTransform: "uppercase",
            }}
          >
            Source-standing changes
          </h2>
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: "0.75rem 0 0",
              display: "flex",
              flexDirection: "column",
              gap: "0.85rem",
            }}
          >
            {standingItems.map((item) => {
              const c = conclusionMap.get(item.conclusionId);
              const s = item.standingId ? standingMap.get(item.standingId) : null;
              const pill = pillStyle(item.status);
              return (
                <li
                  key={item.id}
                  className="portal-card"
                  style={{ padding: "1rem 1.25rem" }}
                  data-testid="source-triage-row"
                >
                  <div
                    style={{
                      display: "flex",
                      gap: "0.75rem",
                      alignItems: "baseline",
                      flexWrap: "wrap",
                    }}
                  >
                    <span
                      style={{
                        background: pill.bg,
                        borderRadius: "999px",
                        color: pill.fg,
                        fontFamily: "'IBM Plex Mono', monospace",
                        fontSize: "0.65rem",
                        letterSpacing: "0.1em",
                        padding: "0.15rem 0.55rem",
                        textTransform: "uppercase",
                      }}
                    >
                      {pill.label}
                    </span>
                    <code style={{ color: "var(--parchment-dim)", fontSize: "0.78rem" }}>
                      {item.sourceId}
                    </code>
                    {s ? (
                      <span style={{ color: "var(--parchment-dim)", fontSize: "0.7rem" }}>
                        via {s.poller} ·{" "}
                        {new Date(s.observedAt).toISOString().slice(0, 10)}
                      </span>
                    ) : null}
                  </div>

                  {s?.reason ? (
                    <p style={{ color: "var(--parchment)", fontSize: "0.85rem", marginTop: "0.45rem" }}>
                      {s.reason}
                    </p>
                  ) : null}

                  <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem", marginTop: "0.6rem" }}>
                    Affects conclusion:{" "}
                    <a
                      href={`/conclusions/${item.conclusionId}`}
                      style={{ color: "var(--gold)" }}
                    >
                      {c?.text?.slice(0, 140) ?? item.conclusionId}
                    </a>
                    {c ? (
                      <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem" }}>
                        ({c.confidenceTier})
                      </span>
                    ) : null}
                  </p>

                  {s?.noticeSourceId ? (
                    <p style={{ color: "var(--parchment-dim)", fontSize: "0.7rem", marginTop: "0.35rem" }}>
                      Notice provenance: <code>{s.noticeSourceId}</code>
                    </p>
                  ) : null}

                  <TriageButtons itemId={item.id} />
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {verdictItems.length > 0 ? (
        <section data-testid="verdict-triage-section" style={{ marginTop: "2rem" }}>
          <h2
            style={{
              color: "var(--parchment)",
              fontFamily: "'Cinzel', serif",
              fontSize: "1rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            Citation-chain verdicts
          </h2>
          <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem", marginTop: "0.4rem" }}>
            The NLI judge found that the cited text does not support the
            firm&apos;s stated claim, or could not confirm it on a load-bearing
            cite. Until each item is confirmed (drop the cite) or overridden
            (keep with a reason), the conclusion is held from publication.
          </p>
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: "0.75rem 0 0",
              display: "flex",
              flexDirection: "column",
              gap: "0.85rem",
            }}
          >
            {verdictItems.map((item) => {
              const c = conclusionMap.get(item.conclusionId);
              const v = item.verdictId ? verdictMap.get(item.verdictId) : null;
              const label = (v?.relationHolds?.toString().toLowerCase() ?? "ambiguous") as CitationVerdictLabel;
              const pill = verdictPill(label);
              return (
                <li
                  key={item.id}
                  className="portal-card"
                  style={{ padding: "1rem 1.25rem" }}
                  data-testid="citation-verdict-triage-row"
                  data-verdict={label}
                >
                  <div
                    style={{
                      display: "flex",
                      gap: "0.75rem",
                      alignItems: "baseline",
                      flexWrap: "wrap",
                    }}
                  >
                    <span
                      style={{
                        background: pill.bg,
                        borderRadius: "999px",
                        color: pill.fg,
                        fontFamily: "'IBM Plex Mono', monospace",
                        fontSize: "0.65rem",
                        letterSpacing: "0.1em",
                        padding: "0.15rem 0.55rem",
                        textTransform: "uppercase",
                      }}
                    >
                      {pill.label}
                    </span>
                    <code style={{ color: "var(--parchment-dim)", fontSize: "0.78rem" }}>
                      {item.sourceId}
                    </code>
                    {v ? (
                      <span style={{ color: "var(--parchment-dim)", fontSize: "0.7rem" }}>
                        firm declared {v.relation.toString().toLowerCase()} · NLI {label} ·{" "}
                        confidence {(v.confidence * 100).toFixed(0)}%
                        {v.cascadeWeight > 0
                          ? ` · cascade weight ${v.cascadeWeight.toFixed(2)}`
                          : ""}
                      </span>
                    ) : null}
                  </div>

                  {v?.statedClaim ? (
                    <p
                      style={{
                        color: "var(--parchment)",
                        fontSize: "0.85rem",
                        marginTop: "0.45rem",
                      }}
                    >
                      <span style={{ color: "var(--parchment-dim)", fontSize: "0.7rem" }}>
                        Firm&apos;s stated claim:{" "}
                      </span>
                      {v.statedClaim}
                    </p>
                  ) : null}

                  {v?.excerptUsed ? (
                    <details style={{ marginTop: "0.5rem" }}>
                      <summary
                        style={{
                          color: "var(--parchment-dim)",
                          cursor: "pointer",
                          fontFamily: "'IBM Plex Mono', monospace",
                          fontSize: "0.7rem",
                          letterSpacing: "0.08em",
                          textTransform: "uppercase",
                        }}
                      >
                        Excerpt judged ({v.excerptUsed.length} chars · model {v.modelVersion})
                      </summary>
                      <p
                        style={{
                          color: "var(--parchment-dim)",
                          fontSize: "0.8rem",
                          marginTop: "0.4rem",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {v.excerptUsed}
                      </p>
                    </details>
                  ) : null}

                  <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem", marginTop: "0.6rem" }}>
                    Affects conclusion:{" "}
                    <a
                      href={`/conclusions/${item.conclusionId}`}
                      style={{ color: "var(--gold)" }}
                    >
                      {c?.text?.slice(0, 140) ?? item.conclusionId}
                    </a>
                    {c ? (
                      <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem" }}>
                        ({c.confidenceTier})
                      </span>
                    ) : null}
                  </p>

                  <TriageButtons itemId={item.id} />
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </main>
  );
}

function TriageButtons({ itemId }: { itemId: string }) {
  return (
    <form
      action="/api/source-triage/decide"
      method="POST"
      style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}
    >
      <input type="hidden" name="id" value={itemId} />
      <button
        name="decision"
        value="confirmed"
        type="submit"
        style={{
          background: "var(--gold)",
          border: "none",
          borderRadius: "4px",
          color: "#1a1208",
          cursor: "pointer",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.72rem",
          letterSpacing: "0.08em",
          padding: "0.4rem 0.85rem",
          textTransform: "uppercase",
        }}
      >
        Confirm propagation
      </button>
      <button
        name="decision"
        value="overridden"
        type="submit"
        style={{
          background: "transparent",
          border: "1px solid var(--gold-dim)",
          borderRadius: "4px",
          color: "var(--gold)",
          cursor: "pointer",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.72rem",
          letterSpacing: "0.08em",
          padding: "0.4rem 0.85rem",
          textTransform: "uppercase",
        }}
      >
        Override (keep weight)
      </button>
      <button
        name="decision"
        value="dismissed"
        type="submit"
        style={{
          background: "transparent",
          border: "1px solid var(--parchment-dim)",
          borderRadius: "4px",
          color: "var(--parchment-dim)",
          cursor: "pointer",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.72rem",
          letterSpacing: "0.08em",
          padding: "0.4rem 0.85rem",
          textTransform: "uppercase",
        }}
      >
        Dismiss
      </button>
    </form>
  );
}
