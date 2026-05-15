import { redirect } from "next/navigation";

import { db } from "@/lib/db";
import { getFounder } from "@/lib/auth";

/**
 * Founder-only follow-digest dashboard.
 *
 * Shows the firm its relationship with public readers without exposing
 * any individual email address. Three views:
 *
 *   1. Subscriber count by scope/cadence (active, paused, pending).
 *   2. The 25 most-recent digest sends — subject, scope label, status,
 *      ack timestamp if the recipient clicked the voluntary "I read
 *      this" link.
 *   3. The 25 most-recent unsubscribes with the optional free-text
 *      reason. Email itself is never rendered — only scope and reason.
 *
 * Per the firm's data discipline, this surface is read-only and
 * intentionally narrow: subscriber email addresses live behind the
 * retention policy and never appear in any publicly-visible counter.
 */

export const dynamic = "force-dynamic";

const SCOPE_LABELS: Record<string, string> = {
  firm: "the firm at large",
  methodology: "methodology",
  domain: "domain",
  conclusion: "conclusion",
};

function scopeLabel(scope: string, scopeKey: string): string {
  const base = SCOPE_LABELS[scope] ?? scope;
  if (scope === "firm" || !scopeKey) return base;
  return `${base} · ${scopeKey}`;
}

function relTime(value: Date | null | undefined): string {
  if (!value) return "—";
  const ms = Date.now() - value.getTime();
  const m = Math.round(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

export default async function SubscribersPage() {
  const founder = await getFounder();
  if (!founder) redirect("/login");
  const organizationId = founder.organizationId;

  const [byScope, byStatus, byCadence, recentSends, recentUnsubs, recentBounces, ackTotals] =
    await Promise.all([
      db.subscriber.groupBy({
        by: ["scope", "scopeKey", "status"],
        where: { organizationId },
        _count: { _all: true },
      }),
      db.subscriber.groupBy({
        by: ["status"],
        where: { organizationId },
        _count: { _all: true },
      }),
      db.subscriber.groupBy({
        by: ["cadence"],
        where: { organizationId, status: "active" },
        _count: { _all: true },
      }),
      db.digestSend.findMany({
        where: { organizationId },
        orderBy: { sentAt: "desc" },
        take: 25,
        include: {
          subscriber: {
            select: { scope: true, scopeKey: true, status: true },
          },
        },
      }),
      db.subscriber.findMany({
        where: { organizationId, status: "unsubscribed" },
        orderBy: { unsubscribedAt: "desc" },
        take: 25,
        select: {
          id: true,
          scope: true,
          scopeKey: true,
          unsubscribedAt: true,
          unsubscribeReason: true,
        },
      }),
      db.subscriberBounce.findMany({
        where: { organizationId },
        orderBy: { occurredAt: "desc" },
        take: 25,
        include: {
          subscriber: { select: { scope: true, scopeKey: true, status: true } },
        },
      }),
      db.digestSend.aggregate({
        where: { organizationId, ackedAt: { not: null } },
        _count: { _all: true },
      }),
    ]);

  const statusCount = (status: string): number =>
    byStatus.find((r) => r.status === status)?._count._all ?? 0;
  const totalSends = await db.digestSend.count({ where: { organizationId } });

  const scopeRows = [...byScope].sort((a, b) => {
    if (a.scope !== b.scope) return a.scope.localeCompare(b.scope);
    return a.scopeKey.localeCompare(b.scopeKey);
  });

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold mb-2">Subscribers</h1>
      <p className="text-sm text-gray-600 mb-6">
        The firm&apos;s relationship with public readers. No individual
        email address is rendered on this page — subscriber email
        addresses live behind the data-retention policy and only the
        firm&apos;s mail transport handles them. Open rate is measured
        voluntarily via the opt-in &ldquo;I read this&rdquo; link.
      </p>

      <section className="mb-8">
        <h2 className="text-lg font-medium mb-2">At a glance</h2>
        <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div className="border rounded p-3">
            <dt className="text-gray-500 text-xs">Active</dt>
            <dd className="text-xl font-semibold">{statusCount("active")}</dd>
          </div>
          <div className="border rounded p-3">
            <dt className="text-gray-500 text-xs">Pending confirm</dt>
            <dd className="text-xl font-semibold">{statusCount("pending")}</dd>
          </div>
          <div className="border rounded p-3">
            <dt className="text-gray-500 text-xs">Paused (bounces)</dt>
            <dd className="text-xl font-semibold">{statusCount("paused")}</dd>
          </div>
          <div className="border rounded p-3">
            <dt className="text-gray-500 text-xs">Unsubscribed</dt>
            <dd className="text-xl font-semibold">{statusCount("unsubscribed")}</dd>
          </div>
        </dl>
        <p className="text-xs text-gray-500 mt-3">
          {totalSends} digest send(s) on record · {ackTotals._count._all}{" "}
          voluntary acknowledgment(s){" "}
          {totalSends > 0
            ? `(${Math.round((ackTotals._count._all / totalSends) * 100)}% ack rate — opt-in lower bound)`
            : ""}
        </p>
      </section>

      <section className="mb-8">
        <h2 className="text-lg font-medium mb-2">Active subscribers by cadence</h2>
        <ul className="text-sm text-gray-700 space-y-1">
          {byCadence.length === 0 ? (
            <li className="text-gray-500">No active subscribers yet.</li>
          ) : (
            byCadence
              .sort((a, b) => a.cadence.localeCompare(b.cadence))
              .map((row) => (
                <li key={row.cadence}>
                  <code className="font-mono">{row.cadence}</code> —{" "}
                  {row._count._all}
                </li>
              ))
          )}
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-lg font-medium mb-2">Subscribers by scope</h2>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left border-b">
              <th className="py-1 pr-3">Scope</th>
              <th className="py-1 pr-3">Status</th>
              <th className="py-1 pr-3 text-right">Count</th>
            </tr>
          </thead>
          <tbody>
            {scopeRows.length === 0 ? (
              <tr>
                <td colSpan={3} className="py-2 text-gray-500">
                  No subscriber rows yet.
                </td>
              </tr>
            ) : (
              scopeRows.map((r) => (
                <tr
                  key={`${r.scope}|${r.scopeKey}|${r.status}`}
                  className="border-b last:border-b-0"
                >
                  <td className="py-1 pr-3">{scopeLabel(r.scope, r.scopeKey)}</td>
                  <td className="py-1 pr-3">
                    <code className="font-mono text-xs">{r.status}</code>
                  </td>
                  <td className="py-1 pr-3 text-right">{r._count._all}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      <section className="mb-8">
        <h2 className="text-lg font-medium mb-2">Recent digest sends</h2>
        {recentSends.length === 0 ? (
          <p className="text-sm text-gray-500">
            No digests have been sent yet. Run{" "}
            <code>noosphere/scripts/run_first_digest.sh</code> to issue
            the first cycle.
          </p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left border-b">
                <th className="py-1 pr-3">Subject</th>
                <th className="py-1 pr-3">Scope</th>
                <th className="py-1 pr-3">Items</th>
                <th className="py-1 pr-3">Status</th>
                <th className="py-1 pr-3">Sent</th>
                <th className="py-1 pr-3">Acked</th>
              </tr>
            </thead>
            <tbody>
              {recentSends.map((s) => (
                <tr key={s.id} className="border-b last:border-b-0">
                  <td className="py-1 pr-3">{s.subject || "(no subject)"}</td>
                  <td className="py-1 pr-3 text-gray-600">
                    {s.subscriber
                      ? scopeLabel(s.subscriber.scope, s.subscriber.scopeKey)
                      : "—"}
                  </td>
                  <td className="py-1 pr-3 text-right">{s.itemCount}</td>
                  <td className="py-1 pr-3">
                    <code className="font-mono text-xs">{s.status}</code>
                  </td>
                  <td className="py-1 pr-3 text-gray-600">{relTime(s.sentAt)}</td>
                  <td className="py-1 pr-3 text-gray-600">
                    {s.ackedAt ? relTime(s.ackedAt) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="mb-8">
        <h2 className="text-lg font-medium mb-2">Recent unsubscribes</h2>
        {recentUnsubs.length === 0 ? (
          <p className="text-sm text-gray-500">No unsubscribes recorded.</p>
        ) : (
          <ul className="text-sm space-y-2">
            {recentUnsubs.map((u) => (
              <li key={u.id} className="border-l-2 border-gray-200 pl-3">
                <div className="text-xs text-gray-500">
                  {scopeLabel(u.scope, u.scopeKey)} · {relTime(u.unsubscribedAt)}
                </div>
                <div className="text-gray-800">
                  {u.unsubscribeReason ? u.unsubscribeReason : <em className="text-gray-400">(no reason given)</em>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-8">
        <h2 className="text-lg font-medium mb-2">Recent delivery failures</h2>
        {recentBounces.length === 0 ? (
          <p className="text-sm text-gray-500">
            No delivery failures recorded. Repeated bounces auto-pause
            the affected subscriber rather than continuing to retry.
          </p>
        ) : (
          <ul className="text-sm space-y-2">
            {recentBounces.map((b) => (
              <li key={b.id} className="border-l-2 border-amber-300 pl-3">
                <div className="text-xs text-gray-500">
                  {b.subscriber
                    ? scopeLabel(b.subscriber.scope, b.subscriber.scopeKey)
                    : "—"}{" "}
                  · <code className="font-mono">{b.kind}</code> ·{" "}
                  {relTime(b.occurredAt)}
                </div>
                <div className="text-gray-800">
                  {b.reason || <em className="text-gray-400">(no diagnostic)</em>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
