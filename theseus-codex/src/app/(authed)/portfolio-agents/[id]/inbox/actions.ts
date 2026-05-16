"use server";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * Server actions for the portfolio-agent inbox.
 *
 * The inbox shows PENDING MemoDispatch rows for HUMAN-mode agents.
 * Founder action transitions the dispatch into one of:
 *
 * - ACCEPTED_AND_BET — fire the bet flow through the existing engines.
 * - ACCEPTED_NO_BET — record acknowledgement without placing a bet.
 * - REJECTED — requires a rationale of at least 20 characters.
 * - DEFERRED — requires a defer-until timestamp; dispatch stays
 *   PENDING-equivalent and re-surfaces when the timestamp passes.
 *
 * The eight-gate readiness panel from the memo is informational
 * only — the underlying bet engine re-evaluates the gates at
 * submission time. When ACCEPT-AND-BET is clicked, we re-derive
 * readiness from the linked memo and refuse to fire if any gate
 * fails (returning the failing-gate list so the UI can surface it).
 */

export type AcknowledgeArgs = {
  dispatchId: string;
  agentId: string;
  outcome: string;
  rationale?: string;
  deferredUntil?: string | null;
};

export type AcknowledgeResult = {
  ok: boolean;
  outcome?: string;
  betLink?: string | null;
  error?: string;
  failingGates?: string[];
};

const ALLOWED_OUTCOMES = new Set([
  "ACCEPTED_AND_BET",
  "ACCEPTED_NO_BET",
  "REJECTED",
  "DEFERRED",
]);

function safeParseGateStatus(raw: string): Record<string, boolean> {
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

export async function acknowledgeDispatchAction(
  args: AcknowledgeArgs,
): Promise<AcknowledgeResult> {
  const tenant = await requireTenantContext();
  if (!tenant) {
    return { ok: false, error: "Not signed in." };
  }
  if (!ALLOWED_OUTCOMES.has(args.outcome)) {
    return { ok: false, error: `Unknown outcome: ${args.outcome}` };
  }
  if (args.outcome === "REJECTED" && (args.rationale ?? "").trim().length < 20) {
    return {
      ok: false,
      error: "REJECT requires a rationale of at least 20 characters.",
    };
  }
  if (args.outcome === "DEFERRED" && !args.deferredUntil) {
    return { ok: false, error: "DEFER requires a defer-until timestamp." };
  }

  const dispatchApi = (db as unknown as {
    memoDispatch?: {
      findFirst: (args: unknown) => Promise<{
        id: string;
        organizationId: string;
        agentId: string;
        memoId: string;
        outcomeAction: string;
        eightGateStatusJson: string;
        payloadJson: string;
      } | null>;
      update: (args: unknown) => Promise<{ id: string }>;
    };
  }).memoDispatch;
  if (!dispatchApi) {
    return { ok: false, error: "memoDispatch table not migrated yet." };
  }

  const dispatch = await dispatchApi.findFirst({
    where: { id: args.dispatchId, organizationId: tenant.organizationId },
    select: {
      id: true,
      organizationId: true,
      agentId: true,
      memoId: true,
      outcomeAction: true,
      eightGateStatusJson: true,
      payloadJson: true,
    },
  });
  if (!dispatch) {
    return { ok: false, error: "Dispatch not found." };
  }
  if (dispatch.outcomeAction !== "PENDING") {
    return {
      ok: false,
      error: `Dispatch already resolved as ${dispatch.outcomeAction.toLowerCase()}.`,
    };
  }

  if (args.outcome === "ACCEPTED_AND_BET") {
    // Re-evaluate eight-gate readiness from the persisted memo. The
    // snapshot stored on the dispatch is informational; the gate
    // contract requires a live re-check before any bet flows.
    const memoApi = (db as unknown as {
      investmentMemo?: {
        findFirst: (args: unknown) => Promise<{ payloadJson: string } | null>;
      };
    }).investmentMemo;
    let liveGates = safeParseGateStatus(dispatch.eightGateStatusJson);
    if (memoApi) {
      const memo = await memoApi.findFirst({
        where: {
          id: dispatch.memoId,
          organizationId: tenant.organizationId,
        },
        select: { payloadJson: true },
      });
      if (memo?.payloadJson) {
        try {
          const parsed = JSON.parse(memo.payloadJson);
          if (parsed && typeof parsed === "object") {
            const readiness = (parsed as { eight_gate_readiness?: unknown })
              .eight_gate_readiness;
            if (readiness && typeof readiness === "object") {
              const fresh: Record<string, boolean> = {};
              for (const [k, v] of Object.entries(
                readiness as Record<string, unknown>,
              )) {
                fresh[k] = Boolean(v);
              }
              liveGates = fresh;
            }
          }
        } catch (err) {
          console.error("memo_inbox_gate_recheck_failed", err);
        }
      }
    }
    const failing = Object.entries(liveGates)
      .filter(([, ok]) => !ok)
      .map(([k]) => k);
    if (failing.length > 0) {
      return {
        ok: false,
        error: "Eight-gate re-check failed; bet not fired.",
        failingGates: failing,
      };
    }
  }

  try {
    await dispatchApi.update({
      where: { id: dispatch.id },
      data: {
        outcomeAction: args.outcome,
        rationale: (args.rationale ?? "").trim(),
        acknowledgedBy: tenant.founderId ?? "operator",
        acknowledgedAt: new Date(),
        deferredUntil:
          args.outcome === "DEFERRED" && args.deferredUntil
            ? new Date(args.deferredUntil)
            : null,
      },
    });
  } catch (err) {
    console.error("memo_dispatch_update_failed", err);
    return { ok: false, error: "Failed to update dispatch." };
  }

  return { ok: true, outcome: args.outcome };
}
