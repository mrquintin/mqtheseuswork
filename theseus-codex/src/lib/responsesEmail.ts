import { db } from "@/lib/db";
import { parsePublicationPayload } from "@/lib/conclusionsRead";
import { sendMail, type MailDeliveryResult, type SendMailInput } from "@/lib/mail";
import { getPublicSiteUrl } from "@/lib/site";

const DEV_FALLBACK_EMAIL = "qmichael444@gmail.com";
const PLACEHOLDER_FOUNDER_ALPHA_EMAIL = "founder-alpha@example.invalid";
const DEFAULT_NOTIFY_FROM = "notify@theseus.local";

export type ResponseEmailResponse = {
  id: string;
  kind: string;
  body: string;
  citationUrl: string;
  submitterEmail: string;
  orcid: string;
  pseudonymous: boolean;
  createdAt?: Date | string;
};

export type ResponseEmailConclusion = {
  id: string;
  slug: string;
  version?: number;
  payloadJson?: string;
  title?: string;
};

export type FounderAlphaRecipient = {
  email: string;
  source: "db" | "env" | "dev-fallback" | "placeholder";
  headers?: Record<string, string>;
};

export async function notifyFounderOfResponse(
  response: ResponseEmailResponse,
  conclusion: ResponseEmailConclusion,
): Promise<MailDeliveryResult> {
  const recipient = await lookupFounderAlphaEmail();
  const from = notifyFromAddress();
  const message = buildResponseEmail({
    response,
    conclusion,
    to: recipient.email,
    from,
    headers: {
      "X-Theseus-Recipient-Source": recipient.source,
      ...(recipient.headers || {}),
    },
  });

  return sendMail(message);
}

export async function lookupFounderAlphaEmail(): Promise<FounderAlphaRecipient> {
  const founder = await getFounderByRole("founder_alpha");
  if (founder?.email?.trim()) {
    return { email: founder.email.trim(), source: "db" };
  }

  const envEmail = process.env.FOUNDER_ALPHA_EMAIL?.trim();
  if (envEmail) {
    return {
      email: envEmail,
      source: isPlaceholderEmail(envEmail) ? "placeholder" : "env",
    };
  }

  if (process.env.NODE_ENV !== "production") {
    return {
      email: DEV_FALLBACK_EMAIL,
      source: "dev-fallback",
      headers: {
        "X-Theseus-Dev-Fallback": "DEV-FALLBACK founder alpha email",
      },
    };
  }

  return {
    email: PLACEHOLDER_FOUNDER_ALPHA_EMAIL,
    source: "placeholder",
  };
}

export async function getFounderByRole(role: string): Promise<{ email: string } | null> {
  return db.founder.findFirst({
    where: { role },
    orderBy: { createdAt: "asc" },
    select: { email: true },
  });
}

export function buildResponseEmail({
  response,
  conclusion,
  to,
  from,
  headers,
}: {
  response: ResponseEmailResponse;
  conclusion: ResponseEmailConclusion;
  to: string;
  from: string;
  headers?: Record<string, string>;
}): SendMailInput {
  const title = conclusionTitle(conclusion);
  const publicUrl = conclusionPublicUrl(conclusion);
  const subject = `[Theseus] Response: ${headerSafe(response.kind)} on "${headerSafe(title)}"`;
  const respondent = respondentLabel(response);
  const replyMailto = replyMailtoUrl(response, title);

  const textLines = [
    `New structured response on Theseus.`,
    "",
    `Respondent: ${respondent}`,
    `Kind: ${response.kind}`,
    `Conclusion: ${title}`,
    `Conclusion URL: ${publicUrl}`,
    `Citation URL: ${response.citationUrl || "none provided"}`,
    replyMailto ? `Reply to this person: ${replyMailto}` : "Reply to this person: unavailable for pseudonymous responses",
    "",
    "Response body:",
    response.body,
  ];

  const html = [
    "<!doctype html>",
    '<html lang="en">',
    "<body>",
    "<h1>New structured response on Theseus</h1>",
    "<dl>",
    `<dt>Respondent</dt><dd>${escapeHtml(respondent)}</dd>`,
    `<dt>Kind</dt><dd>${escapeHtml(response.kind)}</dd>`,
    `<dt>Conclusion</dt><dd><a href="${escapeHtml(publicUrl)}">${escapeHtml(title)}</a></dd>`,
    `<dt>Citation URL</dt><dd>${response.citationUrl ? `<a href="${escapeHtml(response.citationUrl)}">${escapeHtml(response.citationUrl)}</a>` : "none provided"}</dd>`,
    `<dt>Reply</dt><dd>${
      replyMailto
        ? `<a href="${escapeHtml(replyMailto)}">Reply to this person</a>`
        : "unavailable for pseudonymous responses"
    }</dd>`,
    "</dl>",
    "<h2>Response body</h2>",
    `<pre style="white-space:pre-wrap">${escapeHtml(response.body)}</pre>`,
    "</body>",
    "</html>",
  ].join("\n");

  return {
    to,
    from,
    subject,
    html,
    text: textLines.join("\n"),
    headers,
  };
}

export function notifyFromAddress(): string {
  return process.env.THESEUS_NOTIFY_FROM?.trim() || DEFAULT_NOTIFY_FROM;
}

export function conclusionTitle(conclusion: ResponseEmailConclusion): string {
  if (conclusion.title?.trim()) return conclusion.title.trim();
  if (conclusion.payloadJson) {
    return parsePublicationPayload({
      payloadJson: conclusion.payloadJson,
      slug: conclusion.slug,
    }).conclusionText;
  }
  return conclusion.slug;
}

export function conclusionPublicUrl(conclusion: ResponseEmailConclusion): string {
  const version = Number.isFinite(conclusion.version)
    ? Number(conclusion.version)
    : 1;
  return `${getPublicSiteUrl()}/c/${encodeURIComponent(conclusion.slug)}/v/${version}`;
}

function respondentLabel(response: ResponseEmailResponse): string {
  const parts: string[] = [];
  if (response.pseudonymous) {
    parts.push("Pseudonymous respondent");
  } else if (response.submitterEmail.trim()) {
    parts.push(response.submitterEmail.trim());
  } else {
    parts.push("Unknown respondent");
  }
  if (response.orcid.trim()) {
    parts.push(`ORCID ${response.orcid.trim()}`);
  }
  if (response.pseudonymous) {
    parts.push("email withheld from reply link");
  }
  return parts.join(" | ");
}

function replyMailtoUrl(response: ResponseEmailResponse, conclusion: string): string | null {
  if (response.pseudonymous) return null;
  const email = response.submitterEmail.trim();
  if (!email || !email.includes("@")) return null;
  const subject = encodeURIComponent(`Re: your Theseus response on ${conclusion}`);
  return `mailto:${encodeURIComponent(email)}?subject=${subject}`;
}

function isPlaceholderEmail(value: string): boolean {
  const lower = value.trim().toLowerCase();
  return lower.endsWith(".invalid") || lower === PLACEHOLDER_FOUNDER_ALPHA_EMAIL;
}

function headerSafe(value: string): string {
  return value.replace(/[\r\n]+/g, " ").trim();
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
