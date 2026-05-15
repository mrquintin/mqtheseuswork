"use client";

import { useMemo, useState, useTransition } from "react";
import AttentionItem, {
  attentionItemKey,
  type AttentionItemViewModel,
} from "./AttentionItem";
import BulkActionBar from "./BulkActionBar";
import QueueHealthIndicator from "./QueueHealthIndicator";
import {
  ATTENTION_QUEUE_LABELS,
  type AttentionQueueId,
} from "@/lib/attentionShared";
import type { QueueHealth } from "@/lib/attention";
import { Panel, EmptyState } from "@/components/design";
import { color, fontSize, space, tracking } from "@/lib/design/tokens";

/**
 * Founder review surface. The list is server-ranked; the dashboard
 * passes a `daily` budget slice (severity-, age-, and diversity-
 * weighted) plus the `deferred` remainder collapsed under "more", so a
 * populated queue doesn't bury the founder. When only `items` is
 * passed (the standalone /attention page) the whole list renders as
 * the daily slice.
 *
 * Selection + bulk snooze/dismiss live here: a populated queue is
 * unmaintainable one row at a time. Bulk actions stay founder-driven —
 * nothing auto-resolves.
 *
 * `queueHealth` shows whether each producer emits faster than the
 * founder triages; `dismissalRates` flags queues cleared so often they
 * likely need threshold tuning.
 */
export type AttentionQueueProps = {
  items: AttentionItemViewModel[];
  daily?: AttentionItemViewModel[];
  deferred?: AttentionItemViewModel[];
  dailyBudget?: number;
  queueHealth?: QueueHealth[];
  dismissalRates?: Array<{ queue: AttentionQueueId; count: number }>;
  generatedAt?: string;
};

async function postAttentionAction(
  payload: Record<string, unknown>,
): Promise<void> {
  const res = await fetch("/api/founder/attention", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as {
      error?: string | { message?: string };
    };
    const message =
      typeof data.error === "string" ? data.error : data.error?.message;
    throw new Error(message || `HTTP ${res.status}`);
  }
}

export default function AttentionQueue({
  items,
  daily,
  deferred,
  dailyBudget,
  queueHealth = [],
  dismissalRates = [],
  generatedAt,
}: AttentionQueueProps) {
  const [selectedKeys, setSelectedKeys] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [resolvedKeys, setResolvedKeys] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [showDeferred, setShowDeferred] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  // `daily` is the budget slice; fall back to the full list when the
  // caller didn't split it (standalone review page).
  const dailySource = daily ?? items;
  const deferredSource = deferred ?? [];

  const dailyItems = useMemo(
    () => dailySource.filter((item) => !resolvedKeys.has(attentionItemKey(item))),
    [dailySource, resolvedKeys],
  );
  const deferredItems = useMemo(
    () =>
      deferredSource.filter(
        (item) => !resolvedKeys.has(attentionItemKey(item)),
      ),
    [deferredSource, resolvedKeys],
  );

  const total = dailyItems.length + deferredItems.length;
  const visibleByKey = useMemo(() => {
    const map = new Map<string, AttentionItemViewModel>();
    for (const item of [...dailyItems, ...deferredItems]) {
      map.set(attentionItemKey(item), item);
    }
    return map;
  }, [dailyItems, deferredItems]);

  const selectedTargets = useMemo(
    () =>
      Array.from(selectedKeys)
        .map((key) => visibleByKey.get(key))
        .filter((item): item is AttentionItemViewModel => Boolean(item)),
    [selectedKeys, visibleByKey],
  );

  // Highlight any queue cleared >=5 times in the last 30 days — that's
  // the "this queue needs tuning" signal.
  const noisy = dismissalRates.filter((row) => row.count >= 5);

  function toggleSelected(key: string) {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function clearSelection() {
    setSelectedKeys(new Set());
    setBulkError(null);
  }

  function markResolved(keys: string[]) {
    setResolvedKeys((prev) => {
      const next = new Set(prev);
      for (const key of keys) next.add(key);
      return next;
    });
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      for (const key of keys) next.delete(key);
      return next;
    });
  }

  function runBulk(
    buildPayload: (item: AttentionItemViewModel) => Record<string, unknown>,
  ) {
    const targets = selectedTargets;
    if (targets.length === 0) {
      setBulkError("Select at least one item.");
      return;
    }
    setBulkError(null);
    startTransition(async () => {
      try {
        await Promise.all(
          targets.map((item) => postAttentionAction(buildPayload(item))),
        );
        markResolved(targets.map((item) => attentionItemKey(item)));
      } catch (err) {
        setBulkError(err instanceof Error ? err.message : "request_failed");
      }
    });
  }

  function handleBulkSnooze(reason: string, days: number) {
    const snoozedUntil = new Date(
      Date.now() + days * 24 * 60 * 60 * 1000,
    ).toISOString();
    runBulk((item) => ({
      queue: item.queue,
      itemId: item.itemId,
      action: "snooze",
      snoozedUntil,
      reason,
    }));
  }

  function handleBulkDismiss(reason: string) {
    runBulk((item) => ({
      queue: item.queue,
      itemId: item.itemId,
      action: "dismiss",
      reason,
    }));
  }

  const meta =
    daily !== undefined
      ? `today's slice — ${dailyItems.length} of ${total}${
          dailyBudget ? ` (budget ${dailyBudget})` : ""
        }`
      : generatedAt
        ? "sorted by urgency and age"
        : undefined;

  return (
    <Panel
      data-testid="attention-queue"
      aria-label="Founder review queue"
      title="Review queue"
      count={total}
      meta={meta}
      tone="accent"
      footer={
        noisy.length > 0 ? (
          <span data-testid="attention-dismissal-hint">
            <span
              className="mono"
              style={{
                letterSpacing: tracking.ultrawide,
                textTransform: "uppercase",
                color: color.ember,
              }}
            >
              Queue tuning —
            </span>{" "}
            these queues have been cleared often recently:{" "}
            {noisy
              .map(
                (row) => `${ATTENTION_QUEUE_LABELS[row.queue]} (${row.count})`,
              )
              .join(", ")}
            .
          </span>
        ) : undefined
      }
    >
      <QueueHealthIndicator health={queueHealth} />

      {selectedTargets.length > 0 ? (
        <BulkActionBar
          selectedCount={selectedTargets.length}
          isPending={isPending}
          error={bulkError}
          onClearSelection={clearSelection}
          onBulkSnooze={handleBulkSnooze}
          onBulkDismiss={handleBulkDismiss}
        />
      ) : null}

      {total === 0 ? (
        <EmptyState title="No items need review." />
      ) : (
        <>
          <ul
            data-testid="attention-daily"
            style={{ listStyle: "none", margin: 0, padding: 0, fontSize: fontSize.body }}
          >
            {dailyItems.map((item) => (
              <AttentionItem
                key={attentionItemKey(item)}
                item={item}
                selected={selectedKeys.has(attentionItemKey(item))}
                onToggleSelected={toggleSelected}
                onResolved={(key) => markResolved([key])}
              />
            ))}
          </ul>

          {deferredItems.length > 0 ? (
            <div style={{ marginTop: space.sm }}>
              <button
                type="button"
                className="btn btn--quiet"
                data-testid="attention-deferred-toggle"
                aria-expanded={showDeferred}
                onClick={() => setShowDeferred((open) => !open)}
              >
                {showDeferred
                  ? "Hide deferred items"
                  : `${deferredItems.length} more deferred today`}
              </button>
              {showDeferred ? (
                <ul
                  data-testid="attention-deferred"
                  style={{
                    listStyle: "none",
                    margin: `${space.sm} 0 0`,
                    padding: 0,
                    fontSize: fontSize.body,
                  }}
                >
                  {deferredItems.map((item) => (
                    <AttentionItem
                      key={attentionItemKey(item)}
                      item={item}
                      selected={selectedKeys.has(attentionItemKey(item))}
                      onToggleSelected={toggleSelected}
                      onResolved={(key) => markResolved([key])}
                    />
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </Panel>
  );
}
