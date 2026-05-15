import { createHash } from "node:crypto";

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { db } from "@/lib/db";

/**
 * Voluntary "I read this" endpoint for follow-digest emails.
 *
 * The firm rejects tracking pixels, which makes the traditional open
 * rate unmeasurable. This route is the honest replacement: every digest
 * carries a per-cycle one-time link to `/api/public/digest-ack/<token>`,
 * and a click here records a hashed acknowledgment. The raw token is
 * never persisted — we hash it on receipt and look up the matching
 * `DigestSend.ackTokenHash`. That keeps the click attributable to the
 * cycle without retaining a recipient identifier.
 *
 * Idempotent: the first click sets `DigestSend.ackedAt`; subsequent
 * clicks (forwarded mail, multiple devices) append a `DigestAck` row
 * but do not overwrite the original timestamp.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Params = { params: Promise<{ token: string }> };

export async function GET(_req: NextRequest, ctx: Params) {
  const { token } = await ctx.params;
  return record(token);
}

export async function POST(_req: NextRequest, ctx: Params) {
  const { token } = await ctx.params;
  return record(token);
}

async function record(rawToken: string): Promise<NextResponse> {
  const token = String(rawToken || "").trim();
  if (!token) {
    return htmlPage(
      "Acknowledgment link missing token",
      "The link you followed did not carry an acknowledgment token.",
      400,
    );
  }
  const hash = sha256Hex(token);
  const send = await db.digestSend.findFirst({ where: { ackTokenHash: hash } });
  if (!send) {
    return htmlPage(
      "Unknown acknowledgment",
      "We could not match that token to a sent digest. The link may be expired or mistyped — nothing is recorded.",
      404,
    );
  }
  await db.digestAck.create({
    data: {
      organizationId: send.organizationId,
      digestSendId: send.id,
      receivedHash: hash,
    },
  });
  if (!send.ackedAt) {
    await db.digestSend.update({
      where: { id: send.id },
      data: { ackedAt: new Date() },
    });
  }
  return htmlPage(
    "Thank you — acknowledgment recorded",
    "The firm has a hashed record that someone reading this digest opted to confirm. Nothing identifying you is stored against the click.",
    200,
  );
}

function htmlPage(title: string, body: string, status: number): NextResponse {
  const html = [
    "<!doctype html>",
    '<html lang="en"><head><meta charset="utf-8"/>',
    `<title>${escapeHtml(title)}</title></head>`,
    '<body style="font-family:Georgia,serif;max-width:36rem;margin:4rem auto;padding:0 1rem;line-height:1.5;color:#222">',
    `<h1>${escapeHtml(title)}</h1>`,
    `<p>${escapeHtml(body)}</p>`,
    '<p><a href="/">Back to Theseus</a></p>',
    "</body></html>",
  ].join("\n");
  return new NextResponse(html, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

function sha256Hex(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function escapeHtml(value: string): string {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
