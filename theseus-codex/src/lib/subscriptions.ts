import { randomBytes } from "node:crypto";

import { db } from "@/lib/db";
import { sendMail, type MailDeliveryResult, type SendMailInput } from "@/lib/mail";
import { notifyFromAddress } from "@/lib/responsesEmail";
import { getPublicSiteUrl } from "@/lib/site";

export const SUBSCRIBER_SCOPES = ["firm", "methodology", "domain", "conclusion"] as const;
export type SubscriberScope = (typeof SUBSCRIBER_SCOPES)[number];

export const SUBSCRIBER_CADENCES = ["weekly", "immediate", "monthly"] as const;
export type SubscriberCadence = (typeof SUBSCRIBER_CADENCES)[number];

export type SubscribeRequest = {
  email: string;
  scope: SubscriberScope;
  scopeKey?: string;
  cadence?: SubscriberCadence;
};

export type SubscribeResult =
  | { ok: true; status: "pending" | "active"; subscriberId: string }
  | { ok: false; error: string; status?: number };

export function normalizeEmail(raw: string): string {
  return String(raw || "").trim().toLowerCase();
}

export function isValidEmail(raw: string): boolean {
  // Permissive but anchored: one @, no whitespace, dot in domain.
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw);
}

export function normalizeScopeKey(scope: SubscriberScope, scopeKey: string): string {
  if (scope === "firm") return "";
  return String(scopeKey || "").trim().slice(0, 200);
}

export function generateToken(): string {
  return randomBytes(32).toString("base64url");
}

export async function createOrReviveSubscriber(
  organizationId: string,
  request: SubscribeRequest,
): Promise<SubscribeResult> {
  const email = normalizeEmail(request.email);
  if (!email || !isValidEmail(email)) {
    return { ok: false, error: "valid email required", status: 400 };
  }
  if (!SUBSCRIBER_SCOPES.includes(request.scope)) {
    return { ok: false, error: "invalid scope", status: 400 };
  }
  const scopeKey = normalizeScopeKey(request.scope, request.scopeKey ?? "");
  if (request.scope !== "firm" && !scopeKey) {
    return { ok: false, error: "scopeKey required for non-firm scopes", status: 400 };
  }
  const cadence: SubscriberCadence = SUBSCRIBER_CADENCES.includes(
    (request.cadence ?? "weekly") as SubscriberCadence,
  )
    ? (request.cadence ?? "weekly")
    : "weekly";

  const existing = await db.subscriber.findUnique({
    where: {
      organizationId_email_scope_scopeKey: {
        organizationId,
        email,
        scope: request.scope,
        scopeKey,
      },
    },
  });

  if (existing && existing.status === "active") {
    return { ok: true, status: "active", subscriberId: existing.id };
  }

  const confirmToken = generateToken();
  const unsubscribeToken = existing?.unsubscribeToken || generateToken();

  const row = existing
    ? await db.subscriber.update({
        where: { id: existing.id },
        data: {
          status: "pending",
          cadence,
          confirmToken,
          unsubscribeToken,
          unsubscribedAt: null,
          unsubscribeReason: "",
        },
      })
    : await db.subscriber.create({
        data: {
          organizationId,
          email,
          scope: request.scope,
          scopeKey,
          status: "pending",
          cadence,
          confirmToken,
          unsubscribeToken,
        },
      });

  return { ok: true, status: "pending", subscriberId: row.id };
}

export async function confirmSubscriber(
  token: string,
): Promise<{ ok: true; subscriberId: string } | { ok: false; error: string }> {
  if (!token) return { ok: false, error: "token required" };
  const row = await db.subscriber.findFirst({ where: { confirmToken: token } });
  if (!row) return { ok: false, error: "unknown or expired token" };
  if (row.status === "unsubscribed") {
    return { ok: false, error: "subscription was previously unsubscribed; resubscribe again" };
  }
  await db.subscriber.update({
    where: { id: row.id },
    data: {
      status: "active",
      confirmedAt: row.confirmedAt ?? new Date(),
      confirmToken: "",
    },
  });
  return { ok: true, subscriberId: row.id };
}

export async function unsubscribeByToken(
  token: string,
  reason: string,
): Promise<{ ok: true; subscriberId: string } | { ok: false; error: string }> {
  if (!token) return { ok: false, error: "token required" };
  const row = await db.subscriber.findUnique({ where: { unsubscribeToken: token } });
  if (!row) return { ok: false, error: "unknown token" };
  if (row.status === "unsubscribed") {
    return { ok: true, subscriberId: row.id };
  }
  await db.subscriber.update({
    where: { id: row.id },
    data: {
      status: "unsubscribed",
      unsubscribedAt: new Date(),
      unsubscribeReason: String(reason || "").slice(0, 1000),
      confirmToken: "",
    },
  });
  return { ok: true, subscriberId: row.id };
}

export function describeScope(scope: SubscriberScope, scopeKey: string): string {
  switch (scope) {
    case "firm":
      return "the firm at large";
    case "methodology":
      return `methodology · ${scopeKey}`;
    case "domain":
      return `domain · ${scopeKey}`;
    case "conclusion":
      return `conclusion · ${scopeKey}`;
  }
}

export function buildConfirmUrl(token: string): string {
  return `${getPublicSiteUrl()}/api/public/subscribe/confirm?token=${encodeURIComponent(token)}`;
}

export function buildUnsubscribeUrl(token: string): string {
  return `${getPublicSiteUrl()}/api/public/unsubscribe/${encodeURIComponent(token)}`;
}

export function buildConfirmEmail({
  to,
  scope,
  scopeKey,
  confirmToken,
  unsubscribeToken,
}: {
  to: string;
  scope: SubscriberScope;
  scopeKey: string;
  confirmToken: string;
  unsubscribeToken: string;
}): SendMailInput {
  const confirmUrl = buildConfirmUrl(confirmToken);
  const unsubscribeUrl = buildUnsubscribeUrl(unsubscribeToken);
  const scopeLabel = describeScope(scope, scopeKey);
  const subject = `[Theseus] Confirm your subscription: ${scopeLabel}`;
  const text = [
    `You (or someone using ${to}) asked to follow ${scopeLabel} at Theseus.`,
    "",
    "Confirm to start receiving digests:",
    confirmUrl,
    "",
    "If you did not request this, ignore this email — no list change happens",
    "without confirmation. You can also click here to remove this pending",
    "request and any future digests:",
    unsubscribeUrl,
    "",
    "Theseus does not embed tracking pixels in any email it sends.",
  ].join("\n");
  const html = [
    "<!doctype html>",
    '<html lang="en"><body style="font-family:Georgia,serif;line-height:1.5;color:#222">',
    `<p>You (or someone using <code>${escapeHtml(to)}</code>) asked to follow <strong>${escapeHtml(scopeLabel)}</strong> at Theseus.</p>`,
    `<p><a href="${escapeHtml(confirmUrl)}">Confirm to start receiving digests</a>.</p>`,
    "<p>If you did not request this, ignore this email — no list change happens without confirmation. ",
    `You can also <a href="${escapeHtml(unsubscribeUrl)}">remove this pending request</a>.</p>`,
    "<p style=\"font-size:0.85em;color:#555\">Theseus does not embed tracking pixels in any email it sends.</p>",
    "</body></html>",
  ].join("\n");
  return {
    to,
    from: notifyFromAddress(),
    subject,
    text,
    html,
    headers: {
      "List-Unsubscribe": `<${unsubscribeUrl}>`,
      "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    },
  };
}

export async function sendConfirmEmail(input: {
  to: string;
  scope: SubscriberScope;
  scopeKey: string;
  confirmToken: string;
  unsubscribeToken: string;
}): Promise<MailDeliveryResult> {
  return sendMail(buildConfirmEmail(input));
}

function escapeHtml(value: string): string {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
