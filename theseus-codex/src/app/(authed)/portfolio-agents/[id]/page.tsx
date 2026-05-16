import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * `/(authed)/portfolio-agents/[id]` — per-agent detail surface.
 *
 * Shows the agent's subscriptions, recent dispatches, and the
 * per-(topic, question_type) hit rate. The inbox lives at
 * `/portfolio-agents/[id]/inbox` and only HUMAN-mode agents have one.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

type AgentDetail = {
  id: string;
  name: string;
  description: string;
  kind: string;
  status: string;
  defaultBetCeilingUsd: number;
  subscriptionsJson: string;
  createdAt: Date;
  updatedAt: Date;
};

type DispatchRow = {
  id: string;
  memoId: string;
  dispatchedAt: Date;
  outcomeAction: string;
  betLink: string | null;
  betLinkKind: string | null;
  acknowledgedBy: string;
  acknowledgedAt: Date | null;
  rationale: string;
  failureReason: string;
};

async function loadAgent(
  organizationId: string,
  agentId: string,
): Promise<AgentDetail | null> {
  const agentApi = (db as unknown as {
    portfolioAgent?: {
      findFirst: (args: unknown) => Promise<AgentDetail | null>;
    };
  }).portfolioAgent;
  if (!agentApi) return null;
  try {
    return await agentApi.findFirst({
      where: { id: agentId, organizationId },
      select: {
        id: true,
        name: true,
        description: true,
        kind: true,
        status: true,
        defaultBetCeilingUsd: true,
        subscriptionsJson: true,
        createdAt: true,
        updatedAt: true,
      },
    });
  } catch (err) {
    console.error("portfolio_agent_load_failed", err);
    return null;
  }
}

async function loadRecentDispatches(agentId: string): Promise<DispatchRow[]> {
  const dispatchApi = (db as unknown as {
    memoDispatch?: {
      findMany: (args: unknown) => Promise<DispatchRow[]>;
    };
  }).memoDispatch;
  if (!dispatchApi) return [];
  try {
    return await dispatchApi.findMany({
      where: { agentId },
      orderBy: { dispatchedAt: "desc" },
      take: 50,
      select: {
        id: true,
        memoId: true,
        dispatchedAt: true,
        outcomeAction: true,
        betLink: true,
        betLinkKind: true,
        acknowledgedBy: true,
        acknowledgedAt: true,
        rationale: true,
        failureReason: true,
      },
    });
  } catch (err) {
    console.error("portfolio_agent_dispatches_load_failed", err);
    return [];
  }
}

function safeParseSubscriptions(
  raw: string,
): Array<{ topic: string; question_type: string; mode: string | null }> {
  try {
    const parsed = JSON.parse(raw || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.map((entry) => ({
      topic: String(entry?.topic ?? "*"),
      question_type: String(entry?.question_type ?? "—"),
      mode: entry?.mode ? String(entry.mode) : null,
    }));
  } catch {
    return [];
  }
}

function formatDate(value: Date | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toISOString().slice(0, 19).replace("T", " ");
}

function summariseDispatches(rows: DispatchRow[]): {
  total: number;
  pending: number;
  accepted_bet: number;
  rejected: number;
  auto_papered: number;
  failed: number;
} {
  const out = {
    total: rows.length,
    pending: 0,
    accepted_bet: 0,
    rejected: 0,
    auto_papered: 0,
    failed: 0,
  };
  for (const r of rows) {
    if (r.outcomeAction === "PENDING") out.pending += 1;
    else if (r.outcomeAction === "ACCEPTED_AND_BET") out.accepted_bet += 1;
    else if (r.outcomeAction === "REJECTED") out.rejected += 1;
    else if (r.outcomeAction === "AUTO_PAPERED") out.auto_papered += 1;
    else if (r.outcomeAction === "DISPATCH_FAILED") out.failed += 1;
  }
  return out;
}

export default async function PortfolioAgentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login?next=%2Fportfolio-agents");

  const { id } = await params;
  const agent = await loadAgent(tenant.organizationId, id);
  if (!agent) notFound();

  const dispatches = await loadRecentDispatches(agent.id);
  const stats = summariseDispatches(dispatches);
  const subscriptions = safeParseSubscriptions(agent.subscriptionsJson);

  const isHuman = agent.kind === "HUMAN";
  const acknowledged = stats.total - stats.pending;
  const hitRate =
    acknowledged > 0
      ? (
          ((stats.accepted_bet + stats.auto_papered) / acknowledged) *
          100
        ).toFixed(1)
      : null;

  return (
    <main className="authed-prose" data-testid="portfolio-agent-detail-page">
      <header style={{ marginBottom: "1.25rem" }}>
        <Link
          href="/portfolio-agents"
          className="mono"
          style={{ fontSize: "0.78rem", color: "var(--amber-dim)" }}
        >
          ← all portfolio agents
        </Link>
        <h1 style={{ marginTop: "0.4rem" }}>{agent.name}</h1>
        <p className="mono" style={{ color: "var(--amber-dim)" }}>
          {agent.kind.toLowerCase()} · {agent.status.toLowerCase()} · created{" "}
          {formatDate(agent.createdAt)}
        </p>
        {agent.description ? (
          <p style={{ marginTop: "0.5rem" }}>{agent.description}</p>
        ) : null}
      </header>

      <section style={{ marginBottom: "1.25rem" }}>
        <h2>Subscriptions</h2>
        {subscriptions.length === 0 ? (
          <p style={{ color: "var(--amber-dim)" }}>
            No subscriptions yet. Add one with
            <code style={{ marginLeft: "0.4rem" }}>
              noosphere portfolio-agent subscribe --agent {agent.id} --topic
              &quot;...&quot; --question-type INVESTMENT_DECISION
            </code>
            .
          </p>
        ) : (
          <ul className="mono" style={{ fontSize: "0.85rem" }}>
            {subscriptions.map((s, i) => (
              <li key={i}>
                <strong>{s.topic}</strong> · {s.question_type.toLowerCase()}
                {s.mode ? ` · ${s.mode.toLowerCase()}` : " · (agent default)"}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginBottom: "1.25rem" }}>
        <h2>Calibration</h2>
        <table
          className="mono"
          style={{
            borderCollapse: "collapse",
            fontSize: "0.85rem",
            marginTop: "0.5rem",
          }}
        >
          <tbody>
            <tr>
              <td style={{ padding: "0.25rem 1rem 0.25rem 0" }}>
                total dispatches
              </td>
              <td>{stats.total}</td>
            </tr>
            <tr>
              <td style={{ padding: "0.25rem 1rem 0.25rem 0" }}>pending</td>
              <td>{stats.pending}</td>
            </tr>
            <tr>
              <td style={{ padding: "0.25rem 1rem 0.25rem 0" }}>
                accepted-and-bet
              </td>
              <td>{stats.accepted_bet}</td>
            </tr>
            <tr>
              <td style={{ padding: "0.25rem 1rem 0.25rem 0" }}>auto-papered</td>
              <td>{stats.auto_papered}</td>
            </tr>
            <tr>
              <td style={{ padding: "0.25rem 1rem 0.25rem 0" }}>rejected</td>
              <td>{stats.rejected}</td>
            </tr>
            <tr>
              <td style={{ padding: "0.25rem 1rem 0.25rem 0" }}>
                dispatch failed
              </td>
              <td>{stats.failed}</td>
            </tr>
            <tr>
              <td style={{ padding: "0.25rem 1rem 0.25rem 0" }}>
                hit rate (acted/acknowledged)
              </td>
              <td>{hitRate === null ? "—" : `${hitRate}%`}</td>
            </tr>
          </tbody>
        </table>
      </section>

      {isHuman && (
        <p style={{ marginBottom: "1.5rem" }}>
          <Link
            href={`/portfolio-agents/${agent.id}/inbox`}
            className="mono"
            style={{ fontSize: "0.85rem" }}
          >
            → open inbox ({stats.pending} pending)
          </Link>
        </p>
      )}

      <section>
        <h2>Recent dispatches</h2>
        {dispatches.length === 0 ? (
          <p style={{ color: "var(--amber-dim)" }}>
            No dispatches yet. SENT memos matching one of this agent&apos;s
            subscriptions will land here.
          </p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid var(--rule)" }}>
                <th style={{ padding: "0.4rem 0.4rem 0.4rem 0" }}>Memo</th>
                <th style={{ padding: "0.4rem" }}>Outcome</th>
                <th style={{ padding: "0.4rem" }}>Bet</th>
                <th style={{ padding: "0.4rem" }}>By</th>
                <th style={{ padding: "0.4rem" }}>When</th>
              </tr>
            </thead>
            <tbody>
              {dispatches.map((d) => (
                <tr key={d.id} style={{ borderBottom: "1px solid var(--rule)" }}>
                  <td style={{ padding: "0.4rem 0.4rem 0.4rem 0" }}>
                    <Link href={`/inbox/${d.memoId}`}>{d.memoId}</Link>
                    {d.failureReason ? (
                      <div
                        className="mono"
                        style={{
                          fontSize: "0.72rem",
                          color: "var(--amber-dim)",
                        }}
                      >
                        {d.failureReason}
                      </div>
                    ) : null}
                  </td>
                  <td className="mono" style={{ padding: "0.4rem" }}>
                    {d.outcomeAction.toLowerCase()}
                  </td>
                  <td className="mono" style={{ padding: "0.4rem" }}>
                    {d.betLink
                      ? `${(d.betLinkKind || "").toLowerCase()}:${d.betLink}`
                      : "—"}
                  </td>
                  <td className="mono" style={{ padding: "0.4rem" }}>
                    {d.acknowledgedBy || "—"}
                  </td>
                  <td className="mono" style={{ padding: "0.4rem" }}>
                    {formatDate(d.acknowledgedAt || d.dispatchedAt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
