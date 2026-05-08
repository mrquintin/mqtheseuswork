import net from "node:net";
import tls from "node:tls";
import { randomUUID } from "node:crypto";
import os from "node:os";

export type SendMailInput = {
  to: string;
  from: string;
  subject: string;
  html: string;
  text: string;
  headers?: Record<string, string>;
};

export type MailDeliveryResult =
  | { delivered: true; provider: "resend" | "smtp"; id?: string }
  | { delivered: false; reason: string; provider?: "console" };

type ResendSender = (
  apiKey: string,
  message: SendMailInput,
) => Promise<MailDeliveryResult>;

type SmtpSender = (message: SendMailInput) => Promise<MailDeliveryResult>;

let resendSender: ResendSender = sendViaResend;
let smtpSender: SmtpSender = sendViaSmtp;

export function __setMailSendersForTesting(senders: {
  resend?: ResendSender;
  smtp?: SmtpSender;
}) {
  if (senders.resend) resendSender = senders.resend;
  if (senders.smtp) smtpSender = senders.smtp;
}

export function __resetMailSendersForTesting() {
  resendSender = sendViaResend;
  smtpSender = sendViaSmtp;
}

export async function sendMail(
  message: SendMailInput,
): Promise<MailDeliveryResult> {
  if (isPlaceholderRecipient(message.to)) {
    console.warn("[mail] skipped placeholder recipient", {
      to: message.to,
      subject: message.subject,
    });
    return { delivered: false, reason: "placeholder recipient" };
  }

  const resendKey = process.env.RESEND_API_KEY?.trim();
  if (resendKey) {
    return resendSender(resendKey, message);
  }

  if (smtpConfigured()) {
    return smtpSender(message);
  }

  console.info("[mail] no provider configured", {
    to: message.to,
    subject: message.subject,
  });
  return {
    delivered: false,
    reason: "no provider configured",
    provider: "console",
  };
}

function smtpConfigured(): boolean {
  return Boolean(
    process.env.SMTP_HOST?.trim() &&
      process.env.SMTP_PORT?.trim() &&
      process.env.SMTP_USER?.trim() &&
      process.env.SMTP_PASS?.trim(),
  );
}

function isPlaceholderRecipient(value: string): boolean {
  const address = extractAddress(value).toLowerCase();
  return (
    address === "founder-alpha@example.invalid" ||
    address.endsWith(".invalid") ||
    address.endsWith("@example.invalid")
  );
}

async function sendViaResend(
  apiKey: string,
  message: SendMailInput,
): Promise<MailDeliveryResult> {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: message.from,
      to: [message.to],
      subject: cleanHeader(message.subject),
      html: message.html,
      text: message.text,
      headers: message.headers,
    }),
  });

  const payload = (await res.json().catch(() => ({}))) as { id?: string; message?: string };
  if (!res.ok) {
    throw new Error(
      `Resend send failed (${res.status}): ${payload.message || res.statusText}`,
    );
  }
  return { delivered: true, provider: "resend", id: payload.id };
}

async function sendViaSmtp(message: SendMailInput): Promise<MailDeliveryResult> {
  const nodemailer = await loadOptionalNodemailer();
  if (nodemailer) {
    return sendViaNodemailer(nodemailer, message);
  }
  return sendViaSmtpSocket(message);
}

async function sendViaNodemailer(
  nodemailer: { createTransport: (options: unknown) => { sendMail: (message: unknown) => Promise<{ messageId?: string }> } },
  message: SendMailInput,
): Promise<MailDeliveryResult> {
  const host = requiredEnv("SMTP_HOST");
  const port = Number.parseInt(requiredEnv("SMTP_PORT"), 10);
  const secure = port === 465 || envFlag("SMTP_SECURE");
  const starttls =
    !secure &&
    !["0", "false", "no"].includes(
      (process.env.SMTP_STARTTLS || "true").trim().toLowerCase(),
    );
  const transport = nodemailer.createTransport({
    host,
    port,
    secure,
    requireTLS: starttls,
    auth: {
      user: requiredEnv("SMTP_USER"),
      pass: requiredEnv("SMTP_PASS"),
    },
  });
  const result = await transport.sendMail({
    to: message.to,
    from: message.from,
    subject: cleanHeader(message.subject),
    html: message.html,
    text: message.text,
    headers: message.headers,
  });
  return { delivered: true, provider: "smtp", id: result.messageId };
}

async function loadOptionalNodemailer(): Promise<{
  createTransport: (options: unknown) => { sendMail: (message: unknown) => Promise<{ messageId?: string }> };
} | null> {
  try {
    const load = new Function("specifier", "return import(specifier)") as (
      specifier: string,
    ) => Promise<{ default?: unknown; createTransport?: unknown }>;
    const mod = await load("nodemailer");
    const candidate = (mod.default || mod) as {
      createTransport?: unknown;
    };
    return typeof candidate.createTransport === "function"
      ? (candidate as {
          createTransport: (options: unknown) => {
            sendMail: (message: unknown) => Promise<{ messageId?: string }>;
          };
        })
      : null;
  } catch {
    return null;
  }
}

async function sendViaSmtpSocket(message: SendMailInput): Promise<MailDeliveryResult> {
  const host = requiredEnv("SMTP_HOST");
  const port = Number.parseInt(requiredEnv("SMTP_PORT"), 10);
  const user = requiredEnv("SMTP_USER");
  const pass = requiredEnv("SMTP_PASS");
  if (!Number.isFinite(port) || port <= 0) {
    throw new Error("SMTP_PORT must be a positive integer");
  }

  const secure = port === 465 || envFlag("SMTP_SECURE");
  const starttls =
    !secure &&
    !["0", "false", "no"].includes(
      (process.env.SMTP_STARTTLS || "true").trim().toLowerCase(),
    );

  let socket: net.Socket | tls.TLSSocket = secure
    ? tls.connect({ host, port, servername: host, timeout: 20_000 })
    : net.connect({ host, port, timeout: 20_000 });

  let smtp = new SmtpConnection(socket);
  await smtp.expect(220);
  await smtp.command(`EHLO ${smtpDomain()}`, 250);

  if (starttls) {
    await smtp.command("STARTTLS", 220);
    socket = tls.connect({ socket, servername: host });
    smtp = new SmtpConnection(socket);
    await smtp.command(`EHLO ${smtpDomain()}`, 250);
  }

  await smtp.command("AUTH LOGIN", 334);
  await smtp.command(Buffer.from(user).toString("base64"), 334);
  await smtp.command(Buffer.from(pass).toString("base64"), 235);
  await smtp.command(`MAIL FROM:<${extractAddress(message.from)}>`, 250);
  await smtp.command(`RCPT TO:<${extractAddress(message.to)}>`, [250, 251]);
  await smtp.command("DATA", 354);
  await smtp.data(renderSmtpMessage(message));
  await smtp.command("QUIT", [221, 250]).catch(() => undefined);

  return { delivered: true, provider: "smtp" };
}

class SmtpConnection {
  private buffer = "";
  private waiters: Array<(line: string) => void> = [];

  constructor(private socket: net.Socket | tls.TLSSocket) {
    socket.setEncoding("utf8");
    socket.on("data", (chunk) => this.onData(String(chunk)));
    socket.on("error", (error) => {
      while (this.waiters.length) {
        this.waiters.shift()?.(`599 ${error.message}`);
      }
    });
  }

  async command(command: string, expected: number | number[]): Promise<string> {
    this.socket.write(`${command}\r\n`);
    return this.expect(expected);
  }

  async data(message: string): Promise<string> {
    this.socket.write(`${dotStuff(message)}\r\n.\r\n`);
    return this.expect(250);
  }

  async expect(expected: number | number[]): Promise<string> {
    const line = await this.nextReply();
    const code = Number.parseInt(line.slice(0, 3), 10);
    const allowed = Array.isArray(expected) ? expected : [expected];
    if (!allowed.includes(code)) {
      throw new Error(`SMTP expected ${allowed.join("/")} but got: ${line}`);
    }
    return line;
  }

  private onData(chunk: string) {
    this.buffer += chunk;
    const lines = this.buffer.split(/\r?\n/);
    this.buffer = lines.pop() || "";
    for (const line of lines) {
      if (/^\d{3} /.test(line)) {
        this.waiters.shift()?.(line);
      }
    }
  }

  private nextReply(): Promise<string> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("SMTP response timed out")),
        20_000,
      );
      this.waiters.push((line) => {
        clearTimeout(timer);
        resolve(line);
      });
    });
  }
}

function renderSmtpMessage(message: SendMailInput): string {
  const boundary = `theseus-${randomUUID()}`;
  const headers: Record<string, string> = {
    From: cleanHeader(message.from),
    To: cleanHeader(message.to),
    Subject: cleanHeader(message.subject),
    Date: new Date().toUTCString(),
    "Message-ID": `<${randomUUID()}@${smtpDomain()}>`,
    "MIME-Version": "1.0",
    "Content-Type": `multipart/alternative; boundary="${boundary}"`,
    ...(message.headers || {}),
  };

  const headerLines = Object.entries(headers)
    .filter(([, value]) => value)
    .map(([key, value]) => `${cleanHeader(key)}: ${cleanHeader(value)}`);

  return [
    ...headerLines,
    "",
    `--${boundary}`,
    'Content-Type: text/plain; charset="utf-8"',
    "Content-Transfer-Encoding: 8bit",
    "",
    normalizeLineEndings(message.text),
    "",
    `--${boundary}`,
    'Content-Type: text/html; charset="utf-8"',
    "Content-Transfer-Encoding: 8bit",
    "",
    normalizeLineEndings(message.html),
    "",
    `--${boundary}--`,
    "",
  ].join("\r\n");
}

function requiredEnv(key: string): string {
  const value = process.env[key]?.trim();
  if (!value) throw new Error(`${key} is required`);
  return value;
}

function envFlag(key: string): boolean {
  return ["1", "true", "yes"].includes(
    (process.env[key] || "").trim().toLowerCase(),
  );
}

function cleanHeader(value: string): string {
  return String(value).replace(/[\r\n]+/g, " ").trim();
}

function extractAddress(value: string): string {
  const clean = cleanHeader(value);
  const bracketed = clean.match(/<([^>]+)>/)?.[1]?.trim();
  return bracketed || clean;
}

function smtpDomain(): string {
  return (process.env.SMTP_EHLO_DOMAIN || os.hostname() || "localhost")
    .replace(/[^A-Za-z0-9.-]/g, "")
    .slice(0, 253) || "localhost";
}

function normalizeLineEndings(value: string): string {
  return String(value).replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/\n/g, "\r\n");
}

function dotStuff(value: string): string {
  return normalizeLineEndings(value).replace(/^\./gm, "..");
}
