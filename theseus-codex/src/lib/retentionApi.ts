/**
 * Retention policy mirror + operator API client.
 *
 * The canonical retention table lives in Python at
 * `noosphere/noosphere/decay/retention_policies.py`. The values below
 * are a literal mirror, kept in sync by `scripts/check_privacy_page_consistency.py`
 * which is run as part of the deploy build. If you edit the Python
 * table, edit this file too — the build will fail otherwise.
 *
 * The operator UI imports this file for both the public /privacy page
 * (so prose and behavior cannot drift) and the founder-only retention
 * dashboard (which fetches live previews from the runner).
 */

export type LifecycleAction =
  | "delete"
  | "rollup_and_delete"
  | "archive"
  | "delete_with_confirmation"
  | "keep_while_source_exists";

export type FounderOverride =
  | "unrestricted"
  | "confirm_required"
  | "locked";

export type RetentionPolicy = {
  key: string;
  label: string;
  ttlDays: number | null;
  action: LifecycleAction;
  override: FounderOverride;
  autoExecute: boolean;
  privacySummary: string;
  legalBasis: string;
  rollupTarget: string | null;
  tombstone: boolean;
};

export const RETENTION_POLICIES: RetentionPolicy[] = [
  {
    key: "spans",
    label: "Observability spans",
    ttlDays: 30,
    action: "rollup_and_delete",
    override: "unrestricted",
    autoExecute: true,
    privacySummary:
      "Internal trace/span records — used to debug pipelines and track latency — are kept for 30 days. After 30 days the raw rows are deleted; only aggregate per-method timing rollups survive.",
    legalBasis: "firm policy: bounded observability cost",
    rollupTarget: "MethodMetricRollup",
    tombstone: false,
  },
  {
    key: "contact_submissions",
    label: "Public contact-form submissions",
    ttlDays: 180,
    action: "delete",
    override: "unrestricted",
    autoExecute: false,
    privacySummary:
      "Messages sent through the public contact form are kept for 180 days so the firm can follow up on a thread, then deleted. You can request earlier deletion; see the data subject request section below.",
    legalBasis: "firm policy: bounded inbox surface",
    rollupTarget: null,
    tombstone: false,
  },
  {
    key: "public_responses",
    label: "Public responses to published conclusions",
    ttlDays: 2555,
    action: "delete_with_confirmation",
    override: "confirm_required",
    autoExecute: false,
    privacySummary:
      "When you submit a response to a published conclusion, the firm retains your submission for 7 years so the public record of dialogue around that conclusion stays intact. After 7 years, the firm reviews and deletes the raw row with founder confirmation; aggregate counts may persist.",
    legalBasis: "legal: reasonable record of public dialogue",
    rollupTarget: null,
    tombstone: false,
  },
  {
    key: "embeddings",
    label: "Vector embeddings",
    ttlDays: null,
    action: "keep_while_source_exists",
    override: "unrestricted",
    autoExecute: true,
    privacySummary:
      "Vector embeddings exist for as long as the underlying source document exists. When a source is deleted, its embeddings are deleted within 30 days.",
    legalBasis: "firm policy: derivative of source",
    rollupTarget: null,
    tombstone: false,
  },
  {
    key: "transcripts",
    label: "Interview transcripts",
    ttlDays: null,
    action: "delete_with_confirmation",
    override: "confirm_required",
    autoExecute: false,
    privacySummary:
      "Interview transcripts (uploads) are retained indefinitely as part of the firm's working corpus. Deletion requires founder confirmation per record; you can also request deletion via the data subject request channel.",
    legalBasis: "firm policy: research corpus",
    rollupTarget: null,
    tombstone: false,
  },
  {
    key: "draft_conclusions",
    label: "Draft (unpublished) conclusions",
    ttlDays: 90,
    action: "delete",
    override: "unrestricted",
    autoExecute: false,
    privacySummary:
      "Internal draft conclusions that are never published are deleted 90 days after they go stale. Published conclusions are retained as part of the public record.",
    legalBasis: "firm policy: bounded draft surface",
    rollupTarget: null,
    tombstone: false,
  },
  {
    key: "retired_objects",
    label: "Retired claims and conclusions",
    ttlDays: 365,
    action: "archive",
    override: "locked",
    autoExecute: false,
    privacySummary:
      "When a claim or conclusion is retired (refuted or withdrawn), the firm archives it for 1 year with a tombstone marker so the audit trail of what was retracted and why remains visible. After 1 year the archive may be compressed but the tombstone remains permanently.",
    legalBasis: "firm policy: retraction transparency",
    rollupTarget: null,
    tombstone: true,
  },
];

/**
 * Per-policy preview returned by the runner. Mirrors
 * `RetentionPreview.to_dict()` in `retention_runner.py`.
 */
export type RetentionTarget = {
  object_id: string;
  age_days: number;
  reason: string;
};

export type RetentionPreview = {
  policy_key: string;
  label: string;
  action: LifecycleAction;
  auto_execute: boolean;
  confirm_required: boolean;
  to_archive: RetentionTarget[];
  to_delete: RetentionTarget[];
  total: number;
};

export function formatTtl(p: RetentionPolicy): string {
  if (p.ttlDays === null) return "indefinite";
  if (p.ttlDays >= 365 && p.ttlDays % 365 === 0) {
    const years = p.ttlDays / 365;
    return `${years} year${years === 1 ? "" : "s"}`;
  }
  return `${p.ttlDays} days`;
}

/**
 * Live preview fetcher (operator dashboard).
 *
 * The runner exposes a JSON endpoint behind the founder auth gate; in
 * development it can also be invoked via
 * `python -m noosphere.cli decay retention-preview --json` and shimmed
 * through a Next.js API route. The route is intentionally not part of
 * the public surface — only the founder UI calls it.
 */
export async function fetchRetentionPreview(
  fetcher: typeof fetch = fetch,
): Promise<RetentionPreview[]> {
  const res = await fetcher("/api/ops/retention/preview", {
    method: "GET",
    headers: { "content-type": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`retention preview failed: ${res.status}`);
  }
  return (await res.json()) as RetentionPreview[];
}

export async function confirmRetentionRun(
  policyKey: string,
  fetcher: typeof fetch = fetch,
): Promise<{ deleted: number; archived: number; errors: string[] }> {
  const res = await fetcher("/api/ops/retention/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ confirm: [policyKey] }),
  });
  if (!res.ok) {
    throw new Error(`retention run failed: ${res.status}`);
  }
  return (await res.json()) as {
    deleted: number;
    archived: number;
    errors: string[];
  };
}
