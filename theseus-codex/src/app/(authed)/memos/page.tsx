import Link from "next/link";
import { redirect } from "next/navigation";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * `/(authed)/memos` — operator memo inbox.
 *
 * Lists every memo the firm has produced, scoped to the operator's
 * organization, with filters by status. The operator drives lifecycle
 * transitions (DRAFT → UNDER_REVIEW → SENT, or → ARCHIVED, or →
 * PUBLIC) from the per-memo detail page at `/memos/[id]`.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const STATUS_VALUES = [
  "DRAFT",
  "UNDER_REVIEW",
  "SENT",
  "ARCHIVED",
  "PUBLIC",
] as const;
type StatusValue = (typeof STATUS_VALUES)[number];

type AuthedMemoRow = {
  id: string;
  slug: string;
  title: string;
  status: string;
  addressee: string;
  questionType: string;
  createdAt: Date;
  sentAt: Date | null;
  publishedAt: Date | null;
};

function parseStatusFilter(value: string | string[] | undefined): StatusValue | null {
  const single = Array.isArray(value) ? value[0] : value;
  if (!single) return null;
  return (STATUS_VALUES as ReadonlyArray<string>).includes(single)
    ? (single as StatusValue)
    : null;
}

function formatDate(value: Date | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toISOString().slice(0, 10);
}

async function loadMemos(
  organizationId: string,
  status: StatusValue | null,
): Promise<AuthedMemoRow[]> {
  const memoApi = (db as unknown as {
    investmentMemo?: {
      findMany: (args: unknown) => Promise<AuthedMemoRow[]>;
    };
  }).investmentMemo;
  if (!memoApi) return [];
  const where: Record<string, unknown> = { organizationId };
  if (status) where.status = status;
  try {
    return await memoApi.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: 200,
      select: {
        id: true,
        slug: true,
        title: true,
        status: true,
        addressee: true,
        questionType: true,
        createdAt: true,
        sentAt: true,
        publishedAt: true,
      },
    });
  } catch (err) {
    console.error("authed_memos_load_failed", err);
    return [];
  }
}

export default async function AuthedMemosIndexPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login?next=%2Fmemos");
  const params = await searchParams;
  const status = parseStatusFilter(params.status);
  const memos = await loadMemos(tenant.organizationId, status);

  return (
    <main className="authed-prose" data-testid="authed-memos-page">
      <header style={{ marginBottom: "1.5rem" }}>
        <h1>Memo inbox</h1>
        <p className="mono" style={{ color: "var(--amber-dim)" }}>
          Investment memos addressed to portfolio agents and human
          reviewers. Memos in DRAFT or UNDER_REVIEW do NOT trigger bets.
        </p>
        <nav
          className="mono"
          style={{
            display: "flex",
            gap: "0.75rem",
            flexWrap: "wrap",
            fontSize: "0.78rem",
            marginTop: "0.75rem",
          }}
        >
          <Link
            href="/memos"
            style={{ opacity: status === null ? 1 : 0.6 }}
          >
            all
          </Link>
          {STATUS_VALUES.map((value) => (
            <Link
              key={value}
              href={`/memos?status=${value}`}
              style={{ opacity: status === value ? 1 : 0.6 }}
            >
              {value.toLowerCase()}
            </Link>
          ))}
        </nav>
      </header>

      {memos.length === 0 ? (
        <p style={{ color: "var(--amber-dim)" }}>
          No memos in this view.
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
            <tr style={{ textAlign: "left", borderBottom: "1px solid var(--rule)" }}>
              <th style={{ padding: "0.5rem 0.5rem 0.5rem 0" }}>Title</th>
              <th style={{ padding: "0.5rem" }}>Status</th>
              <th style={{ padding: "0.5rem" }}>Type</th>
              <th style={{ padding: "0.5rem" }}>Addressee</th>
              <th style={{ padding: "0.5rem" }}>Created</th>
              <th style={{ padding: "0.5rem" }}>Sent</th>
              <th style={{ padding: "0.5rem" }}>Published</th>
            </tr>
          </thead>
          <tbody>
            {memos.map((memo) => (
              <tr key={memo.id} style={{ borderBottom: "1px solid var(--rule)" }}>
                <td style={{ padding: "0.5rem 0.5rem 0.5rem 0" }}>
                  <Link href={`/memos/${memo.id}`}>{memo.title || "—"}</Link>
                </td>
                <td className="mono" style={{ padding: "0.5rem" }}>
                  {memo.status.toLowerCase()}
                </td>
                <td className="mono" style={{ padding: "0.5rem" }}>
                  {memo.questionType.toLowerCase()}
                </td>
                <td style={{ padding: "0.5rem" }}>{memo.addressee || "—"}</td>
                <td className="mono" style={{ padding: "0.5rem" }}>
                  {formatDate(memo.createdAt)}
                </td>
                <td className="mono" style={{ padding: "0.5rem" }}>
                  {formatDate(memo.sentAt)}
                </td>
                <td className="mono" style={{ padding: "0.5rem" }}>
                  {formatDate(memo.publishedAt)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
