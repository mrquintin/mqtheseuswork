import Link from "next/link";

import { db } from "@/lib/db";
import {
  listAcceptedPrinciples,
  listRecentPrinciples,
  type PrincipleRow,
} from "@/lib/principlesApi";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Knowledge → Principles tab.
 *
 * Surfaces the firm's principle ledger: how many accepted principles
 * exist, how many landed recently, and a shortlist of the most recent
 * additions. Distillation now auto-accepts (no triage gate), so the
 * "Recent principles" link goes to a read-only audit log rather than a
 * founder action surface. The canonical detail page remains at
 * `/principles/[id]`.
 */
export default async function KnowledgePrinciplesTab() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const [recent, accepted, publicCount] = await Promise.all([
    listRecentPrinciples(tenant.organizationId, 30),
    listAcceptedPrinciples(tenant.organizationId),
    db.principle.count({
      where: {
        organizationId: tenant.organizationId,
        publicVisible: true,
        status: "accepted",
      },
    }),
  ]);

  const topAccepted = accepted.slice(0, 8);

  return (
    <main style={{ maxWidth: "1040px", margin: "0 auto", padding: "1.5rem 1.5rem 4rem" }}>
      <header style={{ marginBottom: "1.25rem" }}>
        <h2
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--gold)",
            letterSpacing: "0.08em",
            margin: 0,
          }}
        >
          Principles
        </h2>
        <p
          style={{
            color: "var(--parchment-dim)",
            fontSize: "0.9rem",
            lineHeight: 1.6,
            maxWidth: "44rem",
            margin: "0.35rem 0 0",
          }}
        >
          Abstract rules the firm keeps re-deriving across its conclusions. A
          principle survives when the same logic recurs across domains, not
          when one strong example shows up. Browse the audit log of recent
          additions at{" "}
          <Link href="/principles/queue" style={{ color: "var(--amber)" }}>
            recent principles
          </Link>
          .
        </p>
      </header>

      <CountStrip
        items={[
          { label: "Accepted", value: accepted.length },
          { label: "Recent additions", value: recent.length },
          { label: "Public-visible", value: publicCount },
        ]}
      />

      <section style={{ marginTop: "1.5rem" }}>
        <h3
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.65rem",
            letterSpacing: "0.2em",
            margin: "0 0 0.65rem",
            textTransform: "uppercase",
          }}
        >
          Recently accepted
        </h3>
        {topAccepted.length === 0 ? (
          <EmptyState
            message="No accepted principles yet."
            hint="Principles surface here once the founder accepts a distilled candidate. The distillation pipeline produces them from conclusion clusters."
          />
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "0.6rem" }}>
            {topAccepted.map((p) => (
              <PrincipleCard key={p.id} principle={p} />
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginTop: "1.5rem" }}>
        <h3
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.65rem",
            letterSpacing: "0.2em",
            margin: "0 0 0.65rem",
            textTransform: "uppercase",
          }}
        >
          Transfer graph
        </h3>
        <EmptyState
          message="Principle transfer graph is not yet persisted in this surface."
          hint="The transfer-graph schema (case ↔ principle edges, principle ↔ principle refinements) lives in the noosphere typed contract. UI rendering of that graph will surface here once the backend persists rows."
        />
      </section>
    </main>
  );
}

function CountStrip({ items }: { items: { label: string; value: number }[] }) {
  return (
    <div
      style={{
        display: "grid",
        gap: "0.75rem",
        gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
      }}
    >
      {items.map((item) => (
        <div
          key={item.label}
          className="portal-card"
          style={{ padding: "0.8rem 1rem" }}
        >
          <p
            className="mono"
            style={{
              color: "var(--amber-dim)",
              fontSize: "0.6rem",
              letterSpacing: "0.18em",
              margin: 0,
              textTransform: "uppercase",
            }}
          >
            {item.label}
          </p>
          <strong
            style={{
              color: "var(--parchment)",
              display: "block",
              fontFamily: "'Cinzel', serif",
              fontSize: "1.35rem",
              marginTop: "0.25rem",
            }}
          >
            {item.value}
          </strong>
        </div>
      ))}
    </div>
  );
}

function PrincipleCard({ principle }: { principle: PrincipleRow }) {
  return (
    <li className="portal-card" style={{ padding: "0.85rem 1rem" }}>
      <Link
        href={`/principles/${principle.id}`}
        style={{
          color: "var(--gold)",
          textDecoration: "none",
          fontFamily: "'EB Garamond', serif",
          fontSize: "1rem",
        }}
      >
        {principle.text}
      </Link>
      <div
        className="mono"
        style={{
          color: "var(--parchment-dim)",
          display: "flex",
          flexWrap: "wrap",
          fontSize: "0.6rem",
          gap: "0.7rem",
          letterSpacing: "0.16em",
          marginTop: "0.45rem",
          textTransform: "uppercase",
        }}
      >
        <span>conviction · {principle.convictionScore.toFixed(2)}</span>
        <span>cluster · {principle.clusterConclusionIds.length}</span>
        <span>domains · {principle.domainBreadth}</span>
        {principle.publicVisible ? <span style={{ color: "var(--gold)" }}>public</span> : null}
      </div>
      {principle.domains.length > 0 ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginTop: "0.45rem" }}>
          {principle.domains.map((d) => (
            <span
              key={d}
              className="mono"
              style={{
                border: "1px solid var(--border)",
                color: "var(--parchment-dim)",
                fontSize: "0.58rem",
                letterSpacing: "0.16em",
                padding: "0.15rem 0.5rem",
                textTransform: "uppercase",
              }}
            >
              {d}
            </span>
          ))}
        </div>
      ) : null}
    </li>
  );
}

function EmptyState({ message, hint }: { message: string; hint: string }) {
  return (
    <div className="portal-card" style={{ padding: "1rem 1.1rem" }}>
      <p style={{ color: "var(--parchment-dim)", margin: 0 }}>{message}</p>
      <p
        style={{
          color: "var(--parchment-dim)",
          fontSize: "0.78rem",
          lineHeight: 1.5,
          margin: "0.4rem 0 0",
        }}
      >
        {hint}
      </p>
    </div>
  );
}
