import Link from "next/link";
import { redirect } from "next/navigation";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * `/(authed)/portfolio-agents` — operator surface for portfolio agents.
 *
 * Round 19 prompt 12. Lists every portfolio agent in the organization
 * (HUMAN inboxes, AUTO_PAPER calibration trackers, and AUTO_LIVE
 * queues). The detail page at `/portfolio-agents/[id]` is where
 * subscriptions are configured and the inbox lives.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

type PortfolioAgentRow = {
  id: string;
  name: string;
  description: string;
  kind: string;
  status: string;
  defaultBetCeilingUsd: number;
  subscriptionsJson: string;
  createdAt: Date;
};

type DispatchCountsByAgent = Record<
  string,
  { pending: number; accepted_bet: number; auto_papered: number; total: number }
>;

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

async function loadAgents(organizationId: string): Promise<PortfolioAgentRow[]> {
  const agentApi = (db as unknown as {
    portfolioAgent?: {
      findMany: (args: unknown) => Promise<PortfolioAgentRow[]>;
    };
  }).portfolioAgent;
  if (!agentApi) return [];
  try {
    return await agentApi.findMany({
      where: { organizationId },
      orderBy: { createdAt: "desc" },
      take: 200,
      select: {
        id: true,
        name: true,
        description: true,
        kind: true,
        status: true,
        defaultBetCeilingUsd: true,
        subscriptionsJson: true,
        createdAt: true,
      },
    });
  } catch (err) {
    console.error("portfolio_agents_load_failed", err);
    return [];
  }
}

async function loadDispatchCounts(
  organizationId: string,
): Promise<DispatchCountsByAgent> {
  const dispatchApi = (db as unknown as {
    memoDispatch?: {
      findMany: (args: unknown) => Promise<
        Array<{ agentId: string; outcomeAction: string }>
      >;
    };
  }).memoDispatch;
  if (!dispatchApi) return {};
  try {
    const rows = await dispatchApi.findMany({
      where: { organizationId },
      select: { agentId: true, outcomeAction: true },
      take: 5000,
    });
    const counts: DispatchCountsByAgent = {};
    for (const r of rows) {
      const entry =
        counts[r.agentId] ||
        (counts[r.agentId] = {
          pending: 0,
          accepted_bet: 0,
          auto_papered: 0,
          total: 0,
        });
      entry.total += 1;
      if (r.outcomeAction === "PENDING") entry.pending += 1;
      if (r.outcomeAction === "ACCEPTED_AND_BET") entry.accepted_bet += 1;
      if (r.outcomeAction === "AUTO_PAPERED") entry.auto_papered += 1;
    }
    return counts;
  } catch (err) {
    console.error("portfolio_agent_dispatch_counts_failed", err);
    return {};
  }
}

function hitRateLabel(
  kind: string,
  counts: { pending: number; accepted_bet: number; auto_papered: number; total: number } | undefined,
): string {
  if (!counts) return "—";
  const acknowledged = counts.total - counts.pending;
  if (acknowledged <= 0) return "—";
  if (kind === "AUTO_PAPER") {
    return `${counts.auto_papered}/${counts.total} auto-papered`;
  }
  return `${counts.accepted_bet}/${acknowledged} accepted-and-bet`;
}

export default async function PortfolioAgentsIndexPage() {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login?next=%2Fportfolio-agents");

  const [agents, dispatchCounts] = await Promise.all([
    loadAgents(tenant.organizationId),
    loadDispatchCounts(tenant.organizationId),
  ]);

  return (
    <main className="authed-prose" data-testid="portfolio-agents-page">
      <header style={{ marginBottom: "1.5rem" }}>
        <h1>Portfolio agents</h1>
        <p className="mono" style={{ color: "var(--amber-dim)" }}>
          The seam between SENT memos and real-world bets. HUMAN agents surface
          memos in an inbox; AUTO_PAPER agents auto-fire paper bets (calibration
          data); AUTO_LIVE agents queue live bets for per-bet confirmation in
          the existing operator console.
        </p>
      </header>

      {agents.length === 0 ? (
        <p style={{ color: "var(--amber-dim)" }}>
          No portfolio agents configured yet. Create one with
          <code style={{ marginLeft: "0.4rem" }}>
            noosphere portfolio-agent create --name &quot;...&quot; --kind HUMAN
          </code>
          .
        </p>
      ) : (
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "0.92rem",
          }}
        >
          <thead>
            <tr
              style={{
                textAlign: "left",
                borderBottom: "1px solid var(--rule)",
              }}
            >
              <th style={{ padding: "0.5rem 0.5rem 0.5rem 0" }}>Name</th>
              <th style={{ padding: "0.5rem" }}>Kind</th>
              <th style={{ padding: "0.5rem" }}>Status</th>
              <th style={{ padding: "0.5rem" }}>Subscriptions</th>
              <th style={{ padding: "0.5rem" }}>Pending</th>
              <th style={{ padding: "0.5rem" }}>Hit rate</th>
              <th style={{ padding: "0.5rem" }}>Ceiling (USD)</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((agent) => {
              const subs = safeParseSubscriptions(agent.subscriptionsJson);
              const counts = dispatchCounts[agent.id];
              return (
                <tr
                  key={agent.id}
                  style={{ borderBottom: "1px solid var(--rule)" }}
                >
                  <td style={{ padding: "0.5rem 0.5rem 0.5rem 0" }}>
                    <Link href={`/portfolio-agents/${agent.id}`}>
                      {agent.name}
                    </Link>
                    {agent.description ? (
                      <div
                        className="mono"
                        style={{
                          fontSize: "0.78rem",
                          color: "var(--amber-dim)",
                        }}
                      >
                        {agent.description}
                      </div>
                    ) : null}
                  </td>
                  <td className="mono" style={{ padding: "0.5rem" }}>
                    {agent.kind.toLowerCase()}
                  </td>
                  <td className="mono" style={{ padding: "0.5rem" }}>
                    {agent.status.toLowerCase()}
                  </td>
                  <td style={{ padding: "0.5rem" }}>
                    {subs.length === 0 ? (
                      <span style={{ color: "var(--amber-dim)" }}>—</span>
                    ) : (
                      <ul
                        className="mono"
                        style={{
                          margin: 0,
                          paddingLeft: "1rem",
                          fontSize: "0.78rem",
                        }}
                      >
                        {subs.map((s, i) => (
                          <li key={i}>
                            {s.topic} / {s.question_type.toLowerCase()}
                            {s.mode ? ` (${s.mode.toLowerCase()})` : ""}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td className="mono" style={{ padding: "0.5rem" }}>
                    {counts?.pending ?? 0}
                  </td>
                  <td className="mono" style={{ padding: "0.5rem" }}>
                    {hitRateLabel(agent.kind, counts)}
                  </td>
                  <td className="mono" style={{ padding: "0.5rem" }}>
                    ${agent.defaultBetCeilingUsd.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </main>
  );
}
