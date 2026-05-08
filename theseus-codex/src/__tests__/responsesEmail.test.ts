import { beforeEach, describe, expect, it, vi } from "vitest";

const dbMock = vi.hoisted(() => ({
  founder: {
    findFirst: vi.fn(),
  },
}));

vi.mock("@/lib/db", () => ({
  db: dbMock,
}));

import {
  buildResponseEmail,
  lookupFounderAlphaEmail,
  type ResponseEmailConclusion,
  type ResponseEmailResponse,
} from "@/lib/responsesEmail";
import {
  __resetMailSendersForTesting,
  __setMailSendersForTesting,
  sendMail,
  type SendMailInput,
} from "@/lib/mail";

const ENV_KEYS = [
  "FOUNDER_ALPHA_EMAIL",
  "NODE_ENV",
  "RESEND_API_KEY",
  "SMTP_HOST",
  "SMTP_PASS",
  "SMTP_PORT",
  "SMTP_USER",
  "THESEUS_PUBLIC_SITE_URL",
];

const ORIGINAL_ENV = Object.fromEntries(
  ENV_KEYS.map((key) => [key, process.env[key]]),
);

const responseFixture: ResponseEmailResponse = {
  id: "resp-1",
  kind: "counter_argument",
  body: "This is the respondent's exact body.\nIt includes <angle brackets> & punctuation.",
  citationUrl: "https://example.com/source",
  submitterEmail: "reader@example.com",
  orcid: "0000-0002-1825-0097",
  pseudonymous: false,
  createdAt: new Date("2026-05-08T12:00:00.000Z"),
};

const conclusionFixture: ResponseEmailConclusion = {
  id: "pub-1",
  slug: "falsifiable-inference",
  version: 3,
  payloadJson: JSON.stringify({
    conclusionText: "Inference should stay falsifiable",
  }),
};

const mailFixture: SendMailInput = {
  to: "alpha@example.com",
  from: "notify@theseus.local",
  subject: "Subject",
  html: "<p>Body</p>",
  text: "Body",
};

describe("responses email", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    __resetMailSendersForTesting();
    for (const key of ENV_KEYS) {
      const original = ORIGINAL_ENV[key];
      if (original === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = original;
      }
    }
    process.env.NODE_ENV = "test";
    process.env.THESEUS_PUBLIC_SITE_URL = "https://theseuscodex.com";
  });

  it("builds the founder notification payload from a response and conclusion", () => {
    const message = buildResponseEmail({
      response: responseFixture,
      conclusion: conclusionFixture,
      to: "alpha@example.com",
      from: "notify@theseus.local",
    });

    expect(message.subject).toBe(
      '[Theseus] Response: counter_argument on "Inference should stay falsifiable"',
    );
    expect(message.text).toContain(responseFixture.body);
    expect(message.text).toContain("Respondent: reader@example.com | ORCID 0000-0002-1825-0097");
    expect(message.text).toContain(
      "Conclusion URL: https://theseuscodex.com/c/falsifiable-inference/v/3",
    );
    expect(message.text).toContain("Reply to this person: mailto:");
    expect(message.html).toContain("This is the respondent&#39;s exact body.");
    expect(message.html).toContain("&lt;angle brackets&gt; &amp; punctuation.");
  });

  it("selects Resend when RESEND_API_KEY is set", async () => {
    const calls: string[] = [];
    process.env.RESEND_API_KEY = "resend-key";
    process.env.SMTP_HOST = "smtp.example.test";
    process.env.SMTP_PORT = "587";
    process.env.SMTP_USER = "smtp-user";
    process.env.SMTP_PASS = "smtp-pass";
    __setMailSendersForTesting({
      resend: async (apiKey) => {
        calls.push(`resend:${apiKey}`);
        return { delivered: true, provider: "resend", id: "email-1" };
      },
      smtp: async () => {
        calls.push("smtp");
        return { delivered: true, provider: "smtp" };
      },
    });

    const result = await sendMail(mailFixture);

    expect(result).toEqual({ delivered: true, provider: "resend", id: "email-1" });
    expect(calls).toEqual(["resend:resend-key"]);
  });

  it("falls back to SMTP when only SMTP env is set", async () => {
    const calls: string[] = [];
    delete process.env.RESEND_API_KEY;
    process.env.SMTP_HOST = "smtp.example.test";
    process.env.SMTP_PORT = "587";
    process.env.SMTP_USER = "smtp-user";
    process.env.SMTP_PASS = "smtp-pass";
    __setMailSendersForTesting({
      smtp: async () => {
        calls.push("smtp");
        return { delivered: true, provider: "smtp" };
      },
    });

    const result = await sendMail(mailFixture);

    expect(result).toEqual({ delivered: true, provider: "smtp" });
    expect(calls).toEqual(["smtp"]);
  });

  it("returns the no-provider sentinel when neither Resend nor SMTP is configured", async () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    delete process.env.RESEND_API_KEY;
    delete process.env.SMTP_HOST;
    delete process.env.SMTP_PORT;
    delete process.env.SMTP_USER;
    delete process.env.SMTP_PASS;

    const result = await sendMail(mailFixture);

    expect(result).toMatchObject({
      delivered: false,
      reason: "no provider configured",
    });
    expect(info).toHaveBeenCalledWith(
      "[mail] no provider configured",
      expect.objectContaining({ to: "alpha@example.com" }),
    );
    info.mockRestore();
  });

  it("resolves founder Alpha email in DB, env, then dev-fallback order", async () => {
    process.env.FOUNDER_ALPHA_EMAIL = "env-alpha@example.com";
    dbMock.founder.findFirst.mockResolvedValueOnce({ email: "db-alpha@example.com" });
    await expect(lookupFounderAlphaEmail()).resolves.toMatchObject({
      email: "db-alpha@example.com",
      source: "db",
    });

    dbMock.founder.findFirst.mockResolvedValueOnce(null);
    await expect(lookupFounderAlphaEmail()).resolves.toMatchObject({
      email: "env-alpha@example.com",
      source: "env",
    });

    delete process.env.FOUNDER_ALPHA_EMAIL;
    dbMock.founder.findFirst.mockResolvedValueOnce(null);
    await expect(lookupFounderAlphaEmail()).resolves.toMatchObject({
      email: "qmichael444@gmail.com",
      source: "dev-fallback",
      headers: {
        "X-Theseus-Dev-Fallback": "DEV-FALLBACK founder alpha email",
      },
    });
  });
});
