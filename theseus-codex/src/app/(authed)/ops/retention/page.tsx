"use client";

import { useEffect, useState } from "react";

import {
  confirmRetentionRun,
  fetchRetentionPreview,
  formatTtl,
  RETENTION_POLICIES,
  type RetentionPreview,
  type RetentionPolicy,
} from "@/lib/retentionApi";

/**
 * Founder-only retention dashboard.
 *
 * Renders a live preview of what the runner would archive/delete today,
 * grouped by policy. For policies that require confirmation, the
 * founder can click Confirm to execute *that policy* for *that day*; a
 * missed confirmation does not silently fire on day 2 (the runner
 * re-surveys every run).
 */

const POLICIES_BY_KEY: Record<string, RetentionPolicy> = Object.fromEntries(
  RETENTION_POLICIES.map((p) => [p.key, p]),
);

type RowState = "idle" | "running" | "confirmed" | "error";

export default function RetentionPage() {
  const [previews, setPreviews] = useState<RetentionPreview[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [rowStates, setRowStates] = useState<Record<string, RowState>>({});
  const [rowMessages, setRowMessages] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    fetchRetentionPreview()
      .then((data) => {
        if (!cancelled) setPreviews(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setLoadError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onConfirm(policyKey: string) {
    setRowStates((s) => ({ ...s, [policyKey]: "running" }));
    try {
      const res = await confirmRetentionRun(policyKey);
      setRowStates((s) => ({ ...s, [policyKey]: "confirmed" }));
      setRowMessages((m) => ({
        ...m,
        [policyKey]: `deleted ${res.deleted}, archived ${res.archived}`,
      }));
    } catch (err) {
      setRowStates((s) => ({ ...s, [policyKey]: "error" }));
      setRowMessages((m) => ({
        ...m,
        [policyKey]: (err as Error).message,
      }));
    }
  }

  function onCancel(policyKey: string) {
    setRowStates((s) => ({ ...s, [policyKey]: "idle" }));
    setRowMessages((m) => ({ ...m, [policyKey]: "cancelled for today" }));
  }

  if (loadError) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="text-2xl font-semibold mb-4">Retention</h1>
        <p className="text-red-600">Failed to load preview: {loadError}</p>
      </main>
    );
  }

  if (previews === null) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="text-2xl font-semibold mb-4">Retention</h1>
        <p className="text-gray-500">Loading preview…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold mb-2">Retention</h1>
      <p className="text-sm text-gray-600 mb-6">
        Today&apos;s preview from the lifecycle runner. Auto-execute
        policies have already run; confirm-required policies wait for an
        explicit click. A missed confirmation does <em>not</em> silently
        fire on day 2.
      </p>
      <div className="space-y-4">
        {previews.map((p) => {
          const policy = POLICIES_BY_KEY[p.policy_key];
          const state = rowStates[p.policy_key] ?? "idle";
          const msg = rowMessages[p.policy_key];
          return (
            <section
              key={p.policy_key}
              data-policy-key={p.policy_key}
              className="border rounded p-4"
            >
              <div className="flex items-baseline justify-between gap-3 mb-2">
                <div>
                  <h2 className="text-lg font-medium">
                    {policy?.label ?? p.label}
                  </h2>
                  <p className="text-xs text-gray-500">
                    TTL {policy ? formatTtl(policy) : "—"} · action{" "}
                    <code>{p.action}</code> ·{" "}
                    {p.auto_execute ? "auto-execute" : "confirm-required"}
                  </p>
                </div>
                <div className="text-right text-sm">
                  <div>
                    <span className="font-medium">{p.to_delete.length}</span>{" "}
                    to delete
                  </div>
                  <div>
                    <span className="font-medium">{p.to_archive.length}</span>{" "}
                    to archive
                  </div>
                </div>
              </div>

              {p.total > 0 && (
                <details className="mb-2 text-sm">
                  <summary className="cursor-pointer text-gray-700">
                    Show targets ({p.total})
                  </summary>
                  <ul className="mt-2 ml-4 list-disc text-xs text-gray-600 max-h-48 overflow-y-auto">
                    {p.to_delete.map((t) => (
                      <li key={`del-${t.object_id}`}>
                        <code>{t.object_id}</code> — {t.reason}
                      </li>
                    ))}
                    {p.to_archive.map((t) => (
                      <li key={`arc-${t.object_id}`}>
                        <code>{t.object_id}</code> — archive — {t.reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {!p.auto_execute && p.total > 0 && (
                <div className="flex items-center gap-3 mt-3">
                  <button
                    type="button"
                    onClick={() => onConfirm(p.policy_key)}
                    disabled={state === "running" || state === "confirmed"}
                    className="px-3 py-1 rounded bg-red-600 text-white text-sm disabled:opacity-40"
                  >
                    {state === "running"
                      ? "Running…"
                      : state === "confirmed"
                        ? "Done"
                        : "Confirm"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onCancel(p.policy_key)}
                    disabled={state === "running"}
                    className="px-3 py-1 rounded border text-sm"
                  >
                    Cancel
                  </button>
                  {msg && (
                    <span className="text-xs text-gray-600">{msg}</span>
                  )}
                </div>
              )}

              {p.auto_execute && (
                <p className="text-xs text-green-700">
                  Auto-execute policy — already applied this run.
                </p>
              )}

              {policy?.override === "locked" && (
                <p className="text-xs text-amber-700 mt-1">
                  Override locked — deletion goes through the retirement
                  workflow, not this dashboard.
                </p>
              )}
            </section>
          );
        })}
      </div>
    </main>
  );
}
