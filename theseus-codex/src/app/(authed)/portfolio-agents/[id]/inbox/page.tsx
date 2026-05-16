import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import MemoInboxItem from "@/components/portfolio/MemoInboxItem";
import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * `/(authed)/portfolio-agents/[id]/inbox` — HUMAN-mode inbox.
 *
 * Each PENDING dispatch renders the full memo (10-section view) plus
 * the four operator actions. AUTO_PAPER and AUTO_LIVE agents don't
 * surface an inbox — their dispatches are terminal at fan-out time —
 * so this page redirects back to the detail view if the agent is not
 * HUMAN.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

type DispatchRow = {
  id: string;
  agentId: string;
  memoId: string;
  dispatchedAt: Date;
  outcomeAction: string;
  eightGateStatusJson: string;
};

type MemoLite = {
  id: string;
  title: string;
  questionType: string;
  payloadJson: string;
};

async function loadAgentKind(
  organizationId: string,
  agentId: string,
): Promise<{ id: string; name: string; kind: string } | null> {
  const agentApi = (db as unknown as {
    portfolioAgent?: {
      findFirst: (args: unknown) => Promise<
        { id: string; name: string; kind: string } | null
      >;
    };
  }).portfolioAgent;
  if (!agentApi) return null;
  try {
    return await agentApi.findFirst({
      where: { id: agentId, organizationId },
      select: { id: true, name: true, kind: true },
    });
  } catch (err) {
    console.error("portfolio_agent_inbox_agent_load_failed", err);
    return null;
  }
}

async function loadPendingDispatches(agentId: string): Promise<DispatchRow[]> {
  const dispatchApi = (db as unknown as {
    memoDispatch?: {
      findMany: (args: unknown) => Promise<DispatchRow[]>;
    };
  }).memoDispatch;
  if (!dispatchApi) return [];
  try {
    return await dispatchApi.findMany({
      where: { agentId, outcomeAction: "PENDING" },
      orderBy: { dispatchedAt: "desc" },
      take: 100,
      select: {
        id: true,
        agentId: true,
        memoId: true,
        dispatchedAt: true,
        outcomeAction: true,
        eightGateStatusJson: true,
      },
    });
  } catch (err) {
    console.error("portfolio_agent_inbox_dispatches_failed", err);
    return [];
  }
}

async function loadMemosForDispatches(
  organizationId: string,
  memoIds: string[],
): Promise<Record<string, MemoLite>> {
  if (memoIds.length === 0) return {};
  const memoApi = (db as unknown as {
    investmentMemo?: {
      findMany: (args: unknown) => Promise<MemoLite[]>;
    };
  }).investmentMemo;
  if (!memoApi) return {};
  try {
    const rows = await memoApi.findMany({
      where: { id: { in: memoIds }, organizationId },
      select: {
        id: true,
        title: true,
        questionType: true,
        payloadJson: true,
      },
    });
    const out: Record<string, MemoLite> = {};
    for (const r of rows) out[r.id] = r;
    return out;
  } catch (err) {
    console.error("portfolio_agent_inbox_memos_load_failed", err);
    return {};
  }
}

function safeParseGates(raw: string): Record<string, boolean> {
  try {
    const parsed = JSON.parse(raw || "{}");
    if (!parsed || typeof parsed !== "object") return {};
    const out: Record<string, boolean> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      out[k] = Boolean(v);
    }
    return out;
  } catch {
    return {};
  }
}

function memoDetailsFromPayload(payloadJson: string): {
  tldr: string;
  body: string;
} {
  try {
    const parsed = JSON.parse(payloadJson || "{}");
    if (!parsed || typeof parsed !== "object") return { tldr: "", body: "" };
    const p = parsed as { tldr?: string; body_markdown?: string };
    return {
      tldr: typeof p.tldr === "string" ? p.tldr : "",
      body: typeof p.body_markdown === "string" ? p.body_markdown : "",
    };
  } catch {
    return { tldr: "", body: "" };
  }
}

export default async function PortfolioAgentInboxPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login?next=%2Fportfolio-agents");

  const { id } = await params;
  const agent = await loadAgentKind(tenant.organizationId, id);
  if (!agent) notFound();

  if (agent.kind !== "HUMAN") {
    return (
      <main className="authed-prose" data-testid="portfolio-agent-inbox-page">
        <header style={{ marginBottom: "1rem" }}>
          <Link
            href={`/portfolio-agents/${agent.id}`}
            className="mono"
            style={{ fontSize: "0.78rem", color: "var(--amber-dim)" }}
          >
            ← {agent.name}
          </Link>
          <h1 style={{ marginTop: "0.4rem" }}>No inbox</h1>
        </header>
        <p style={{ color: "var(--amber-dim)" }}>
          Only HUMAN-mode portfolio agents have an inbox. This agent is{" "}
          {agent.kind.toLowerCase()} — its dispatches are terminal at fan-out
          time.
        </p>
      </main>
    );
  }

  const dispatches = await loadPendingDispatches(agent.id);
  const memos = await loadMemosForDispatches(
    tenant.organizationId,
    dispatches.map((d) => d.memoId),
  );

  return (
    <main className="authed-prose" data-testid="portfolio-agent-inbox-page">
      <header style={{ marginBottom: "1.25rem" }}>
        <Link
          href={`/portfolio-agents/${agent.id}`}
          className="mono"
          style={{ fontSize: "0.78rem", color: "var(--amber-dim)" }}
        >
          ← {agent.name}
        </Link>
        <h1 style={{ marginTop: "0.4rem" }}>Inbox</h1>
        <p className="mono" style={{ color: "var(--amber-dim)" }}>
          {dispatches.length} pending memo
          {dispatches.length === 1 ? "" : "s"}. ACCEPT-AND-BET re-evaluates the
          eight-gate readiness at click time — failing gates are surfaced
          inline and the bet is not fired.
        </p>
      </header>

      {dispatches.length === 0 ? (
        <p style={{ color: "var(--amber-dim)" }}>
          No pending memos. New SENT memos matching a subscription on this
          agent will land here.
        </p>
      ) : (
        dispatches.map((d) => {
          const memo = memos[d.memoId];
          const gates = safeParseGates(d.eightGateStatusJson);
          const details = memoDetailsFromPayload(memo?.payloadJson || "");
          return (
            <MemoInboxItem
              key={d.id}
              dispatchId={d.id}
              agentId={agent.id}
              memoId={d.memoId}
              memoTitle={memo?.title || ""}
              memoTldr={details.tldr}
              questionType={memo?.questionType || ""}
              dispatchedAt={d.dispatchedAt.toISOString()}
              eightGateStatus={gates}
              bodyMarkdown={details.body}
            />
          );
        })
      )}
    </main>
  );
}
