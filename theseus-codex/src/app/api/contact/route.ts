import { createHash } from "crypto";
import { NextResponse } from "next/server";

import { db } from "@/lib/db";
import { sanitizeText } from "@/lib/sanitizeText";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Public inbound contact endpoint.
 *
 * Route table:
 *   POST /api/contact
 *
 * Design note: this endpoint intentionally writes only to
 * ContactSubmission. It does not send email from the firm; SMTP and
 * deliverability are deferred until the founder explicitly configures an
 * outbound channel or domain-level forwarding.
 */

type ContactBody = {
  fromName?: unknown;
  fromEmail?: unknown;
  subject?: unknown;
  body?: unknown;
  company_url?: unknown;
};

type FieldErrors = Partial<
  Record<"fromName" | "fromEmail" | "subject" | "body", string>
>;

const EMAIL_RE =
  /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/;
const MAX_USER_AGENT_LENGTH = 500;
const RATE_LIMIT_WINDOW_MS = 24 * 60 * 60 * 1000;
const RATE_LIMIT_MAX = 5;

export async function POST(req: Request) {
  const body = await readContactBody(req);

  if (filledHoneypot(body.company_url)) {
    return NextResponse.json({ ok: true }, { status: 200 });
  }

  const validated = validateContactBody(body);
  if (!validated.ok) {
    return NextResponse.json(
      {
        ok: false,
        error: "Validation failed.",
        fieldErrors: validated.fieldErrors,
      },
      { status: 400 },
    );
  }

  const now = new Date();
  const ipHash = hashClientIp(clientIp(req), now);
  const recentCount = await db.contactSubmission.count({
    where: {
      ipHash,
      createdAt: { gte: new Date(now.getTime() - RATE_LIMIT_WINDOW_MS) },
    },
  });

  if (recentCount >= RATE_LIMIT_MAX) {
    return NextResponse.json(
      {
        ok: false,
        error: "Too many contact submissions from this network. Try again later.",
      },
      { status: 429 },
    );
  }

  const row = await db.contactSubmission.create({
    data: {
      fromName: validated.value.fromName,
      fromEmail: validated.value.fromEmail,
      subject: validated.value.subject,
      body: validated.value.body,
      organizationId: null,
      ipHash,
      userAgent: optionalUserAgent(req.headers.get("user-agent")),
    },
    select: { id: true },
  });

  return NextResponse.json({ ok: true, id: row.id }, { status: 200 });
}

async function readContactBody(req: Request): Promise<ContactBody> {
  const contentType = req.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await req.json().catch(() => ({}))) as ContactBody;
  }

  const formData = await req.formData().catch(() => null);
  if (!formData) return {};

  return {
    fromName: formData.get("fromName"),
    fromEmail: formData.get("fromEmail"),
    subject: formData.get("subject"),
    body: formData.get("body"),
    company_url: formData.get("company_url"),
  };
}

function validateContactBody(
  body: ContactBody,
):
  | {
      ok: true;
      value: {
        fromName: string;
        fromEmail: string;
        subject: string | null;
        body: string;
      };
    }
  | { ok: false; fieldErrors: FieldErrors } {
  const fieldErrors: FieldErrors = {};
  const fromName = plainText(body.fromName);
  const fromEmail = emailText(body.fromEmail);
  const subject = optionalPlainText(body.subject);
  const messageBody = plainText(body.body);

  if (!fromName) {
    fieldErrors.fromName = "Name is required.";
  } else if (fromName.length > 100) {
    fieldErrors.fromName = "Name must be 100 characters or fewer.";
  }

  if (!fromEmail) {
    fieldErrors.fromEmail = "Email is required.";
  } else if (fromEmail.length > 254 || !isValidEmail(fromEmail)) {
    fieldErrors.fromEmail = "Enter a valid email address.";
  }

  if (subject && subject.length > 200) {
    fieldErrors.subject = "Subject must be 200 characters or fewer.";
  }

  if (!messageBody || messageBody.length < 10) {
    fieldErrors.body = "Message must be at least 10 characters.";
  } else if (messageBody.length > 4000) {
    fieldErrors.body = "Message must be 4000 characters or fewer.";
  }

  if (Object.keys(fieldErrors).length > 0) {
    return { ok: false, fieldErrors };
  }

  return {
    ok: true,
    value: {
      fromName,
      fromEmail,
      subject: subject || null,
      body: messageBody,
    },
  };
}

function plainText(value: unknown): string {
  if (typeof value !== "string") return "";
  return stripHtml(sanitizeText(value)).trim();
}

function optionalPlainText(value: unknown): string {
  if (value == null) return "";
  return plainText(value);
}

function emailText(value: unknown): string {
  if (typeof value !== "string") return "";
  return sanitizeText(value).trim().toLowerCase();
}

function stripHtml(value: string): string {
  return value
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<\/?[^>]+>/g, "");
}

function isValidEmail(value: string): boolean {
  if (!EMAIL_RE.test(value)) return false;
  try {
    const url = new URL(`mailto:${value}`);
    return (
      url.protocol === "mailto:" &&
      decodeURIComponent(url.pathname) === value
    );
  } catch {
    return false;
  }
}

function filledHoneypot(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

function clientIp(req: Request): string {
  return (
    firstHeaderValue(req.headers.get("cf-connecting-ip")) ||
    firstHeaderValue(req.headers.get("x-forwarded-for")) ||
    firstHeaderValue(req.headers.get("x-real-ip")) ||
    "unknown"
  );
}

function firstHeaderValue(value: string | null): string | null {
  const first = value?.split(",")[0]?.trim();
  return first || null;
}

function hashClientIp(ip: string, now: Date): string {
  return createHash("sha256")
    .update(`${ip}${dailySalt(now)}`)
    .digest("hex");
}

function dailySalt(now: Date): string {
  const day = now.toISOString().slice(0, 10);
  const secret =
    process.env.CONTACT_DAILY_SALT_SECRET ||
    process.env.SESSION_SECRET ||
    "dev-contact-salt";
  return `${day}:${secret}`;
}

function optionalUserAgent(value: string | null): string | null {
  const clean = sanitizeText(value || "").trim();
  return clean ? clean.slice(0, MAX_USER_AGENT_LENGTH) : null;
}
