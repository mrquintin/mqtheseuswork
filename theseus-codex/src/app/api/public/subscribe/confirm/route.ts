import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { confirmSubscriber } from "@/lib/subscriptions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const token = req.nextUrl.searchParams.get("token") ?? "";
  const result = await confirmSubscriber(token);
  if (!result.ok) {
    return new NextResponse(renderPage("Confirmation failed", result.error), {
      status: 400,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }
  return new NextResponse(
    renderPage(
      "Subscription confirmed",
      "You are on the list. Digests will arrive on the cadence you chose. Every email contains a one-click unsubscribe link.",
    ),
    { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } },
  );
}

function renderPage(title: string, body: string): string {
  return [
    "<!doctype html>",
    '<html lang="en"><head><meta charset="utf-8"/>',
    `<title>${escape(title)}</title>`,
    "</head><body style=\"font-family:Georgia,serif;max-width:36rem;margin:4rem auto;padding:0 1rem;line-height:1.5;color:#222\">",
    `<h1>${escape(title)}</h1>`,
    `<p>${escape(body)}</p>`,
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
