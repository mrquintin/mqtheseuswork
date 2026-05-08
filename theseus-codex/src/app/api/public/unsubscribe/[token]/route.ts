import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { unsubscribeByToken } from "@/lib/subscriptions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Params = { params: Promise<{ token: string }> };

export async function GET(_req: NextRequest, ctx: Params) {
  const { token } = await ctx.params;
  const result = await unsubscribeByToken(token, "");
  return htmlResponse(result);
}

export async function POST(req: NextRequest, ctx: Params) {
  const { token } = await ctx.params;
  let reason = "";
  const ct = req.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    const body = (await req.json().catch(() => null)) as { reason?: string } | null;
    reason = String(body?.reason ?? "");
  } else {
    const form = await req.formData().catch(() => null);
    reason = String(form?.get("reason") ?? "");
  }
  const result = await unsubscribeByToken(token, reason);
  return htmlResponse(result);
}

function htmlResponse(result: { ok: true; subscriberId: string } | { ok: false; error: string }) {
  if (!result.ok) {
    return new NextResponse(
      renderPage("Unsubscribe failed", result.error),
      { status: 400, headers: { "Content-Type": "text/html; charset=utf-8" } },
    );
  }
  return new NextResponse(
    renderPage(
      "You are unsubscribed",
      "You will receive no further digests for this subscription. Optionally, tell us why so the firm can read the signal:",
      true,
    ),
    { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } },
  );
}

function renderPage(title: string, body: string, withReasonForm = false): string {
  const form = withReasonForm
    ? [
        '<form method="post" style="margin-top:1rem">',
        '<textarea name="reason" rows="3" cols="40" placeholder="Optional: why are you unsubscribing?" style="width:100%;font:inherit"></textarea>',
        '<button type="submit" style="margin-top:0.5rem">Send</button>',
        "</form>",
      ].join("\n")
    : "";
  return [
    "<!doctype html>",
    '<html lang="en"><head><meta charset="utf-8"/>',
    `<title>${escape(title)}</title></head>`,
    '<body style="font-family:Georgia,serif;max-width:36rem;margin:4rem auto;padding:0 1rem;line-height:1.5;color:#222">',
    `<h1>${escape(title)}</h1>`,
    `<p>${escape(body)}</p>`,
    form,
    '<p><a href="/">Back to Theseus</a></p>',
    "</body></html>",
  ].join("\n");
}

function escape(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
