import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";

/**
 * `/memos/[slug]` — the public detail page for a published memo.
 *
 * Renders the full 10-section investment-memo structure as it was
 * persisted by the synthesizer's memo builder. The markdown body is
 * the canonical source; we render it through a restrained markdown
 * pass tuned for memo prose (headings, lists, tables, inline code).
 *
 * Operator-only memos (DRAFT, UNDER_REVIEW, SENT, ARCHIVED) NEVER
 * surface here — the `where` clause filters to status = PUBLIC. The
 * matching authed surface at `/(authed)/memos/[id]` is the operator
 * read-write view.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

type MemoRow = {
  id: string;
  slug: string;
  title: string;
  addressee: string;
  questionType: string;
  status: string;
  pdfPath: string | null;
  publishedAt: Date | null;
  createdAt: Date;
  payloadJson: string;
};

type MemoPayload = {
  body_markdown?: string;
  tldr?: string;
  confidence_low?: number;
  confidence_high?: number;
  what_would_update_us?: string;
  implied_bet?: Record<string, unknown> | null;
  eight_gate_readiness?: Record<string, boolean>;
};

function parsePayload(raw: string): MemoPayload {
  try {
    const parsed = JSON.parse(raw) as MemoPayload;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

async function loadMemo(slug: string): Promise<MemoRow | null> {
  const memoApi = (db as unknown as {
    investmentMemo?: {
      findFirst: (args: unknown) => Promise<MemoRow | null>;
    };
  }).investmentMemo;
  if (!memoApi) return null;
  try {
    return await memoApi.findFirst({
      where: { OR: [{ slug }, { id: slug }], status: "PUBLIC" },
      select: {
        id: true,
        slug: true,
        title: true,
        addressee: true,
        questionType: true,
        status: true,
        pdfPath: true,
        publishedAt: true,
        createdAt: true,
        payloadJson: true,
      },
    });
  } catch (err) {
    console.error("memo_detail_load_failed", err);
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const memo = await loadMemo(slug);
  if (!memo) {
    return { title: "Memo not found · Theseus" };
  }
  const payload = parsePayload(memo.payloadJson);
  return {
    title: `${memo.title} · Theseus memos`,
    description: payload.tldr || `Theseus investment memo — ${memo.title}.`,
    openGraph: {
      title: memo.title,
      description: payload.tldr ?? "",
      type: "article",
    },
  };
}

// Minimal markdown renderer. Headings, paragraphs, lists, tables, and
// inline emphasis. Larger doc-style memos are still readable; the PDF
// at `pdfPath` is the canonical typeset rendering.
function renderInline(text: string): string {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(
      /\[([^\]]+)\]\(([^)\s]+)\)/g,
      '<a href="$2">$1</a>',
    );
}

function renderMarkdown(body: string): string {
  const lines = body.split("\n");
  const out: string[] = [];
  let listKind: "ul" | "ol" | null = null;
  let inTable = false;

  function closeList(): void {
    if (listKind) {
      out.push(`</${listKind}>`);
      listKind = null;
    }
  }
  function closeTable(): void {
    if (inTable) {
      out.push("</tbody></table>");
      inTable = false;
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (!line.trim()) {
      closeList();
      closeTable();
      continue;
    }
    const heading = /^(#{1,3})\s+(?:\d+\.\s+)?(.+)$/.exec(line);
    if (heading) {
      closeList();
      closeTable();
      const level = heading[1].length;
      out.push(`<h${level + 1}>${renderInline(heading[2])}</h${level + 1}>`);
      continue;
    }
    if (line.startsWith("|") && line.includes("|", 1)) {
      const cells = line
        .split("|")
        .slice(1, -1)
        .map((cell) => cell.trim());
      const isSeparator = cells.every((cell) => /^[-: ]+$/.test(cell));
      if (isSeparator) continue;
      if (!inTable) {
        out.push('<table><thead><tr>');
        for (const cell of cells) out.push(`<th>${renderInline(cell)}</th>`);
        out.push("</tr></thead><tbody>");
        inTable = true;
      } else {
        out.push("<tr>");
        for (const cell of cells) out.push(`<td>${renderInline(cell)}</td>`);
        out.push("</tr>");
      }
      continue;
    }
    closeTable();
    const ulMatch = /^[-*]\s+(.+)$/.exec(line);
    const olMatch = /^(\d+)\.\s+(.+)$/.exec(line);
    if (ulMatch) {
      if (listKind !== "ul") {
        closeList();
        out.push("<ul>");
        listKind = "ul";
      }
      out.push(`<li>${renderInline(ulMatch[1])}</li>`);
      continue;
    }
    if (olMatch) {
      if (listKind !== "ol") {
        closeList();
        out.push("<ol>");
        listKind = "ol";
      }
      out.push(`<li>${renderInline(olMatch[2])}</li>`);
      continue;
    }
    closeList();
    out.push(`<p>${renderInline(line)}</p>`);
  }
  closeList();
  closeTable();
  return out.join("\n");
}

export default async function MemoDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const memo = await loadMemo(slug);
  if (!memo) notFound();

  const founder = await getFounder();
  const payload = parsePayload(memo.payloadJson);
  const rendered = renderMarkdown(payload.body_markdown ?? "");

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-prose" data-testid="memo-detail">
        <div style={{ marginBottom: "1.25rem" }}>
          <Link href="/memos" className="mono" style={{ fontSize: "0.78rem" }}>
            ← all memos
          </Link>
        </div>
        <article
          className="memo-body"
          dangerouslySetInnerHTML={{ __html: rendered }}
        />
        <footer
          style={{
            borderTop: "1px solid var(--rule)",
            marginTop: "2.5rem",
            paddingTop: "1rem",
            fontSize: "0.85rem",
          }}
        >
          <p>
            <strong>What we did.</strong>{" "}
            The portfolio agent named above received this memo when it
            was sent. Whether the implied bet was taken — and what
            happened next — is recorded in the agent&apos;s execution log
            (link surfaces here once prompt 12 lands).
          </p>
          {memo.pdfPath && (
            <p>
              <a href={`/${memo.pdfPath}`} rel="noopener">
                Download PDF
              </a>
            </p>
          )}
        </footer>
      </main>
    </>
  );
}
