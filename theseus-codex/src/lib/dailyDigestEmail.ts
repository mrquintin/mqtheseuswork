import { db } from "@/lib/db";
import {
  ATTENTION_QUEUE_LABELS,
  listAttentionForFounder,
  type AttentionItem,
  type AttentionQueueId,
  type AttentionSeverity,
} from "@/lib/attention";
import {
  sendMail,
  type MailDeliveryResult,
  type SendMailInput,
} from "@/lib/mail";
import { notifyFromAddress } from "@/lib/responsesEmail";
import { getPublicSiteUrl } from "@/lib/site";
import type { TenantContext } from "@/lib/tenant";

/**
 * Daily morning digest of open high-severity attention items.
 *
 * Opt-in per founder via `Founder.dailyDigestOptIn`. The digest is
 * sent to founders who have opted in and have at least one
 * high-severity item open at send time; founders with zero open
 * high-severity items get NO email — silence is the right signal
 * when the queue is clear.
 *
 * Each item links back to the founder dashboard, which is the
 * single surface for triage. We deliberately do not deeplink to the
 * underlying queue page — the dashboard is where snooze/dismiss
 * lives.
 */

export type DailyDigestRecipient = {
  organizationId: string;
  organizationSlug: string;
  founderId: string;
  email: string;
  founderName: string;
  founderUsername: string;
};

export type DailyDigestPayload = {
  recipient: DailyDigestRecipient;
  highSeverityItems: AttentionItem[];
  generatedAt: Date;
};

const DASHBOARD_PATH = "/dashboard";

export async function listDigestRecipients(): Promise<DailyDigestRecipient[]> {
  const founders = await db.founder.findMany({
    where: { dailyDigestOptIn: true },
    select: {
      id: true,
      email: true,
      name: true,
      displayName: true,
      username: true,
      organizationId: true,
      organization: { select: { slug: true } },
    },
  });
  return founders
    .filter((row) => row.email && row.email.includes("@"))
    .map((row) => ({
      organizationId: row.organizationId,
      organizationSlug: row.organization?.slug ?? "",
      founderId: row.id,
      email: row.email,
      founderName: row.displayName?.trim() || row.name,
      founderUsername: row.username,
    }));
}

function recipientToTenantContext(
  recipient: DailyDigestRecipient,
): TenantContext {
  return {
    organizationId: recipient.organizationId,
    organizationSlug: recipient.organizationSlug,
    founderId: recipient.founderId,
    founderName: recipient.founderName,
    founderUsername: recipient.founderUsername,
    role: "founder",
  };
}

export async function buildDigestPayload(
  recipient: DailyDigestRecipient,
  now: Date = new Date(),
): Promise<DailyDigestPayload> {
  const tenant = recipientToTenantContext(recipient);
  const listing = await listAttentionForFounder(tenant, now);
  return {
    recipient,
    highSeverityItems: listing.items.filter((item) => item.severity === "high"),
    generatedAt: listing.generatedAt,
  };
}

export function buildDigestEmail(
  payload: DailyDigestPayload,
  options: { from?: string; siteUrl?: string } = {},
): SendMailInput {
  const from = options.from || notifyFromAddress();
  const siteUrl = (options.siteUrl ?? getPublicSiteUrl()).replace(/\/+$/, "");
  const dashboardUrl = `${siteUrl}${DASHBOARD_PATH}`;
  const items = payload.highSeverityItems;
  const subject = `[Theseus] ${items.length} item${items.length === 1 ? "" : "s"} need${items.length === 1 ? "s" : ""} your attention`;

  const textLines = [
    `Good morning, ${payload.recipient.founderName}.`,
    "",
    items.length === 1
      ? "1 high-severity item is open in the founder attention queue:"
      : `${items.length} high-severity items are open in the founder attention queue:`,
    "",
    ...items.map((item) => formatItemText(item, payload.generatedAt, siteUrl)),
    "",
    `Open the dashboard: ${dashboardUrl}`,
    "",
    "You are receiving this because daily digest emails are enabled for your account.",
  ];

  const html = [
    "<!doctype html>",
    '<html lang="en"><body>',
    `<p>Good morning, ${escapeHtml(payload.recipient.founderName)}.</p>`,
    `<p>${items.length} high-severity item${items.length === 1 ? "" : "s"} open in the founder attention queue:</p>`,
    "<ol>",
    ...items.map((item) => formatItemHtml(item, payload.generatedAt, siteUrl)),
    "</ol>",
    `<p><a href="${escapeHtml(dashboardUrl)}">Open the dashboard →</a></p>`,
    "<p style=\"font-size:0.8em;color:#666\">Daily digest enabled on your account.</p>",
    "</body></html>",
  ].join("\n");

  return {
    to: payload.recipient.email,
    from,
    subject,
    html,
    text: textLines.join("\n"),
    headers: {
      "X-Theseus-Recipient-Source": "daily-digest",
      "X-Theseus-Founder-Id": payload.recipient.founderId,
    },
  };
}

function formatItemText(
  item: AttentionItem,
  now: Date,
  siteUrl: string,
): string {
  const queueLabel = ATTENTION_QUEUE_LABELS[item.queue];
  const age = formatAge(now.getTime() - item.createdAt.getTime());
  const link = absoluteLink(siteUrl, item.link);
  return `- [${queueLabel} · ${age}] ${item.preview}\n  ${link}`;
}

function formatItemHtml(
  item: AttentionItem,
  now: Date,
  siteUrl: string,
): string {
  const queueLabel = escapeHtml(ATTENTION_QUEUE_LABELS[item.queue]);
  const age = escapeHtml(formatAge(now.getTime() - item.createdAt.getTime()));
  const preview = escapeHtml(item.preview);
  const link = escapeHtml(absoluteLink(siteUrl, item.link));
  return `<li><strong>${queueLabel} · ${age}</strong> — ${preview} <a href="${link}">open</a></li>`;
}

function absoluteLink(siteUrl: string, link: string): string {
  if (link.startsWith("http")) return link;
  if (link.startsWith("/")) return `${siteUrl}${link}`;
  return `${siteUrl}/${link}`;
}

function formatAge(ms: number): string {
  if (ms <= 0) return "just now";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export type DailyDigestRunResult = {
  founderId: string;
  email: string;
  itemCount: number;
  delivery?: MailDeliveryResult;
  skipped?: "no_high_severity" | "no_recipients";
};

/**
 * Send the digest to every opted-in founder. Founders with zero
 * high-severity items get skipped — silence when there's nothing to
 * say is the right behaviour for a morning summary.
 */
export async function sendDailyDigests(
  now: Date = new Date(),
): Promise<DailyDigestRunResult[]> {
  const recipients = await listDigestRecipients();
  if (recipients.length === 0) return [];
  const results: DailyDigestRunResult[] = [];
  for (const recipient of recipients) {
    const payload = await buildDigestPayload(recipient, now);
    if (payload.highSeverityItems.length === 0) {
      results.push({
        founderId: recipient.founderId,
        email: recipient.email,
        itemCount: 0,
        skipped: "no_high_severity",
      });
      continue;
    }
    const message = buildDigestEmail(payload);
    const delivery = await sendMail(message);
    results.push({
      founderId: recipient.founderId,
      email: recipient.email,
      itemCount: payload.highSeverityItems.length,
      delivery,
    });
  }
  return results;
}

/** Test-only export — re-exposed so the test file can drive ranking
 * without hitting the network. */
export type { AttentionSeverity, AttentionQueueId };
