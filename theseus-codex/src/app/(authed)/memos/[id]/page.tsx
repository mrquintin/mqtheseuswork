import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

/**
 * `/(authed)/memos/[id]` — operator detail page.
 *
 * Renders the persisted memo body and exposes the lifecycle actions
 * the operator drives:
 *
 *   - **Send** transitions DRAFT/UNDER_REVIEW → SENT, fires the
 *     portfolio-agent webhook (prompt 12 wires the actual dispatch).
 *   - **Archive** marks the memo ARCHIVED — no action taken.
 *   - **Publish** marks the memo PUBLIC — appears on `/memos`.
 *
 * The operator can re-address the memo from this page before sending.
 * Sending is NEVER automatic — the synthesizer always emits in DRAFT.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const VALID_STATUSES = new Set([
  "DRAFT",
  "UNDER_REVIEW",
  "SENT",
  "ARCHIVED",
  "PUBLIC",
]);

type AuthedMemoRow = {
  id: string;
  slug: string;
  title: string;
  status: string;
  addressee: string;
  questionType: string;
  pdfPath: string | null;
  mdPath: string | null;
  createdAt: Date;
  updatedAt: Date;
  sentAt: Date | null;
  publishedAt: Date | null;
  archivedAt: Date | null;
  organizationId: string;
  payloadJson: string;
};

type MemoPayload = {
  body_markdown?: string;
  tldr?: string;
  confidence_low?: number;
  confidence_high?: number;
  eight_gate_readiness?: Record<string, boolean>;
  implied_bet?: Record<string, unknown> | null;
};

function parsePayload(raw: string): MemoPayload {
  try {
    const parsed = JSON.parse(raw) as MemoPayload;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

async function loadMemo(id: string, organizationId: string): Promise<AuthedMemoRow | null> {
  const memoApi = (db as unknown as {
    investmentMemo?: {
      findFirst: (args: unknown) => Promise<AuthedMemoRow | null>;
    };
  }).investmentMemo;
  if (!memoApi) return null;
  try {
    return await memoApi.findFirst({
      where: { id, organizationId },
      select: {
        id: true,
        slug: true,
        title: true,
        status: true,
        addressee: true,
        questionType: true,
        pdfPath: true,
        mdPath: true,
        createdAt: true,
        updatedAt: true,
        sentAt: true,
        publishedAt: true,
        archivedAt: true,
        organizationId: true,
        payloadJson: true,
      },
    });
  } catch (err) {
    console.error("authed_memo_detail_load_failed", err);
    return null;
  }
}

async function transitionMemo(formData: FormData): Promise<void> {
  "use server";
  const tenant = await requireTenantContext();
  if (!tenant) return;
  const id = String(formData.get("id") ?? "");
  const targetStatus = String(formData.get("status") ?? "");
  const addressee = formData.get("addressee");
  if (!id || !VALID_STATUSES.has(targetStatus)) return;

  const memoApi = (db as unknown as {
    investmentMemo?: {
      findFirst: (args: unknown) => Promise<AuthedMemoRow | null>;
      update: (args: unknown) => Promise<unknown>;
    };
  }).investmentMemo;
  if (!memoApi) return;

  const existing = await memoApi.findFirst({
    where: { id, organizationId: tenant.organizationId },
    select: { id: true, status: true },
  });
  if (!existing) return;

  const data: Record<string, unknown> = { status: targetStatus };
  if (typeof addressee === "string" && addressee.trim()) {
    data.addressee = addressee.trim();
  }
  const now = new Date();
  if (targetStatus === "SENT") data.sentAt = now;
  if (targetStatus === "PUBLIC") data.publishedAt = now;
  if (targetStatus === "ARCHIVED") data.archivedAt = now;

  await memoApi.update({ where: { id }, data });
  revalidatePath(`/memos/${id}`);
  revalidatePath("/memos");
}

function renderInline(text: string): string {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>');
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
      const cells = line.split("|").slice(1, -1).map((cell) => cell.trim());
      const isSeparator = cells.every((cell) => /^[-: ]+$/.test(cell));
      if (isSeparator) continue;
      if (!inTable) {
        out.push("<table><thead><tr>");
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
    const ul = /^[-*]\s+(.+)$/.exec(line);
    const ol = /^(\d+)\.\s+(.+)$/.exec(line);
    if (ul) {
      if (listKind !== "ul") {
        closeList();
        out.push("<ul>");
        listKind = "ul";
      }
      out.push(`<li>${renderInline(ul[1])}</li>`);
      continue;
    }
    if (ol) {
      if (listKind !== "ol") {
        closeList();
        out.push("<ol>");
        listKind = "ol";
      }
      out.push(`<li>${renderInline(ol[2])}</li>`);
      continue;
    }
    closeList();
    out.push(`<p>${renderInline(line)}</p>`);
  }
  closeList();
  closeTable();
  return out.join("\n");
}

export default async function AuthedMemoDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");
  const { id } = await params;
  const memo = await loadMemo(id, tenant.organizationId);
  if (!memo) notFound();

  const payload = parsePayload(memo.payloadJson);
  const rendered = renderMarkdown(payload.body_markdown ?? "");
  const status = memo.status;
  const canSend = status === "DRAFT" || status === "UNDER_REVIEW";
  const canPublish = status === "SENT" || status === "DRAFT" || status === "UNDER_REVIEW";
  const canArchive = status !== "ARCHIVED" && status !== "PUBLIC";

  return (
    <main className="authed-prose" data-testid="authed-memo-detail">
      <div style={{ marginBottom: "1rem" }}>
        <Link href="/memos" className="mono" style={{ fontSize: "0.78rem" }}>
          ← memo inbox
        </Link>
      </div>
      <header
        style={{
          marginBottom: "1.5rem",
          borderBottom: "1px solid var(--rule)",
          paddingBottom: "1rem",
        }}
      >
        <h1 style={{ marginBottom: "0.25rem" }}>{memo.title}</h1>
        <div
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.78rem",
            display: "flex",
            gap: "1.25rem",
            flexWrap: "wrap",
            marginTop: "0.5rem",
          }}
        >
          <span>status · {status.toLowerCase()}</span>
          <span>type · {memo.questionType.toLowerCase()}</span>
          <span>addressee · {memo.addressee || "—"}</span>
          <span>
            confidence ·{" "}
            {payload.confidence_low !== undefined &&
            payload.confidence_high !== undefined
              ? `${payload.confidence_low.toFixed(2)}–${payload.confidence_high.toFixed(2)}`
              : "—"}
          </span>
        </div>
      </header>

      <section
        style={{
          marginBottom: "1.5rem",
          padding: "1rem",
          border: "1px solid var(--rule)",
          borderRadius: 6,
        }}
      >
        <h2 style={{ marginTop: 0 }}>Operator actions</h2>
        <form
          action={transitionMemo}
          style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}
        >
          <input type="hidden" name="id" value={memo.id} />
          <label style={{ fontSize: "0.85rem" }}>
            Addressee:&nbsp;
            <input
              type="text"
              name="addressee"
              defaultValue={memo.addressee}
              style={{ width: "20rem", maxWidth: "100%" }}
            />
          </label>
          {canSend && (
            <button type="submit" name="status" value="SENT">
              Send to portfolio agent
            </button>
          )}
          {canPublish && (
            <button type="submit" name="status" value="PUBLIC">
              Publish
            </button>
          )}
          {canArchive && (
            <button type="submit" name="status" value="ARCHIVED">
              Archive
            </button>
          )}
        </form>
        {memo.pdfPath && (
          <p style={{ marginTop: "0.75rem" }}>
            <a href={`/${memo.pdfPath}`}>Download PDF</a>
          </p>
        )}
      </section>

      <article
        className="memo-body"
        dangerouslySetInnerHTML={{ __html: rendered }}
      />
    </main>
  );
}
