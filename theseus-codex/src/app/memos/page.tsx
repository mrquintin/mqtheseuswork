import type { Metadata } from "next";
import Link from "next/link";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";

/**
 * `/memos` — the public reader surface for investment memos the firm
 * has chosen to publish. Only memos with `status = PUBLIC` are
 * exposed; DRAFT, UNDER_REVIEW, SENT, and ARCHIVED memos are
 * operator-only and rendered under `/(authed)/memos`.
 *
 * Round 19 prompt 11 ships the canonical 10-section investment-memo
 * format. The list page surfaces the title, TL;DR, addressee, and
 * publish date; the detail page (`/memos/[slug]`) renders the full
 * structure with a downloadable PDF.
 */

export const metadata: Metadata = {
  title: "Memos · Theseus",
  description:
    "Theseus investment memos — selected analyses the firm has chosen to make public. Each memo carries a TL;DR, the governing principles, the reasoning chain, and the implied bet.",
  openGraph: {
    title: "Theseus · investment memos",
    description:
      "Selected investment memos made public. The 10-section investment-memo format: TL;DR, governing principles, observed inputs, reasoning chain, implied bet, provenance audit.",
    type: "website",
  },
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

type PublicMemoRow = {
  id: string;
  slug: string;
  title: string;
  addressee: string;
  questionType: string;
  publishedAt: Date | null;
  createdAt: Date;
  payloadJson: string;
};

type MemoPayload = {
  tldr?: string;
  confidence_low?: number;
  confidence_high?: number;
};

function parsePayload(raw: string): MemoPayload {
  try {
    const parsed = JSON.parse(raw) as MemoPayload;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function formatBand(low?: number, high?: number): string | null {
  if (low === undefined || high === undefined) return null;
  if (!Number.isFinite(low) || !Number.isFinite(high)) return null;
  return `${low.toFixed(2)}–${high.toFixed(2)}`;
}

function formatDate(value: Date | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toISOString().slice(0, 10);
}

async function loadPublicMemos(): Promise<PublicMemoRow[]> {
  // Use the typed Prisma client. Once `prisma generate` has run with
  // the new schema, `db.investmentMemo` is available; until then this
  // page renders an empty list (production deploys run `prisma
  // generate` as part of the build).
  const memoApi = (db as unknown as {
    investmentMemo?: {
      findMany: (args: unknown) => Promise<PublicMemoRow[]>;
    };
  }).investmentMemo;
  if (!memoApi) return [];
  try {
    return await memoApi.findMany({
      where: { status: "PUBLIC" },
      orderBy: { publishedAt: "desc" },
      take: 50,
      select: {
        id: true,
        slug: true,
        title: true,
        addressee: true,
        questionType: true,
        publishedAt: true,
        createdAt: true,
        payloadJson: true,
      },
    });
  } catch (err) {
    console.error("memos_index_load_failed", err);
    return [];
  }
}

export default async function MemosIndexPage() {
  const founder = await getFounder();
  const memos = await loadPublicMemos();

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-prose" data-testid="memos-page">
        <header style={{ marginBottom: "2.5rem" }}>
          <h1>Memos</h1>
          <p className="mono" style={{ color: "var(--amber-dim)" }}>
            Selected investment memos. Each one carries a TL;DR, the
            governing principles, the reasoning chain, the implied bet
            (if any), and the full provenance audit.
          </p>
        </header>

        {memos.length === 0 ? (
          <p style={{ color: "var(--amber-dim)" }}>
            No public memos yet. The firm publishes selectively — when
            a memo's reasoning is mature enough to teach, it appears
            here.
          </p>
        ) : (
          <ul className="memo-index" style={{ listStyle: "none", padding: 0 }}>
            {memos.map((memo) => {
              const payload = parsePayload(memo.payloadJson);
              const band = formatBand(
                payload.confidence_low,
                payload.confidence_high,
              );
              return (
                <li
                  key={memo.id}
                  style={{
                    borderBottom: "1px solid var(--rule)",
                    padding: "1.25rem 0",
                  }}
                >
                  <Link
                    href={`/memos/${memo.slug || memo.id}`}
                    style={{
                      fontSize: "1.25rem",
                      fontWeight: 600,
                      textDecoration: "none",
                    }}
                  >
                    {memo.title || "Untitled memo"}
                  </Link>
                  <p style={{ marginTop: "0.5rem" }}>{payload.tldr ?? ""}</p>
                  <div
                    className="mono"
                    style={{
                      color: "var(--amber-dim)",
                      fontSize: "0.78rem",
                      marginTop: "0.75rem",
                      display: "flex",
                      gap: "1.25rem",
                      flexWrap: "wrap",
                    }}
                  >
                    <span>type · {memo.questionType.toLowerCase()}</span>
                    <span>addressee · {memo.addressee || "—"}</span>
                    {band && <span>confidence · {band}</span>}
                    <span>published · {formatDate(memo.publishedAt)}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </>
  );
}
