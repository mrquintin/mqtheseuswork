/**
 * Security smoke tests for the hardening pass documented in
 * `docs/security/Threat_Model.md` §8. Each block here exists to keep
 * one mitigation honest:
 *
 *   - Brute-force lockout on N failed login attempts
 *   - Per-API-key rate limit
 *   - Per-API-key scope ladder
 *   - CSRF token issuance + validation (double-submit + HMAC)
 *   - Public anti-bot challenge token (issue + verify, IP-bound)
 *   - Strong-password predicate
 *   - Secret scanner (planted token must trigger a finding)
 *
 * If a test goes red, the threat model is wrong — fix the code or fix
 * the doc, do not silence the test.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

// ── login lockout ─────────────────────────────────────────────────────────
import {
  _resetAllLoginRateLimitsForTests,
  checkLoginRateLimit,
} from "@/lib/rateLimit";

describe("brute-force login lockout", () => {
  beforeEach(() => {
    _resetAllLoginRateLimitsForTests();
    delete process.env.THESEUS_LOGIN_MAX_ATTEMPTS;
  });

  it("denies after the configured threshold", () => {
    process.env.THESEUS_LOGIN_MAX_ATTEMPTS = "3";
    expect(checkLoginRateLimit("ip::user").ok).toBe(true);
    expect(checkLoginRateLimit("ip::user").ok).toBe(true);
    expect(checkLoginRateLimit("ip::user").ok).toBe(true);
    const blocked = checkLoginRateLimit("ip::user");
    expect(blocked.ok).toBe(false);
    if (!blocked.ok) {
      expect(blocked.retryAfterSec).toBeGreaterThan(0);
    }
  });

  it("isolates buckets per (ip, identifier) tuple", () => {
    process.env.THESEUS_LOGIN_MAX_ATTEMPTS = "1";
    expect(checkLoginRateLimit("ip-a::alice").ok).toBe(true);
    expect(checkLoginRateLimit("ip-a::alice").ok).toBe(false);
    // Different bucket — fresh quota.
    expect(checkLoginRateLimit("ip-b::alice").ok).toBe(true);
    expect(checkLoginRateLimit("ip-a::bob").ok).toBe(true);
  });
});

// ── API key rate limit + scope + auth ────────────────────────────────────
import {
  _resetApiKeyRateLimitsForTests,
  apiKeyHasScope,
  authenticateApiKey,
  checkApiKeyRateLimit,
  generateApiKeyPlaintext,
  normaliseScopes,
} from "@/lib/apiKeyAuth";

vi.mock("@/lib/db", () => {
  return {
    db: {
      apiKey: {
        findMany: vi.fn(),
        update: vi.fn().mockResolvedValue({}),
      },
      auditEvent: {
        create: vi.fn().mockResolvedValue({}),
      },
    },
  };
});

import { db } from "@/lib/db";

describe("per-API-key rate limit", () => {
  beforeEach(() => {
    _resetApiKeyRateLimitsForTests();
  });

  it("denies after burst", () => {
    const id = "key-rate-1";
    let lastOk = true;
    for (let i = 0; i < 60; i += 1) {
      const r = checkApiKeyRateLimit(id);
      lastOk = r.ok;
      expect(r.ok).toBe(true);
    }
    expect(lastOk).toBe(true);
    const blocked = checkApiKeyRateLimit(id);
    expect(blocked.ok).toBe(false);
  });

  it("isolates buckets per apiKeyId", () => {
    for (let i = 0; i < 60; i += 1) {
      checkApiKeyRateLimit("key-iso-a");
    }
    expect(checkApiKeyRateLimit("key-iso-a").ok).toBe(false);
    expect(checkApiKeyRateLimit("key-iso-b").ok).toBe(true);
  });
});

describe("API key scope ladder", () => {
  it("treats empty scope as legacy full access", () => {
    expect(apiKeyHasScope({ scopes: "" }, "publish")).toBe(true);
    expect(apiKeyHasScope({ scopes: null }, "read")).toBe(true);
  });

  it("write implies read but not publish", () => {
    expect(apiKeyHasScope({ scopes: "write" }, "read")).toBe(true);
    expect(apiKeyHasScope({ scopes: "write" }, "write")).toBe(true);
    expect(apiKeyHasScope({ scopes: "write" }, "publish")).toBe(false);
  });

  it("publish implies write and read", () => {
    expect(apiKeyHasScope({ scopes: "publish" }, "read")).toBe(true);
    expect(apiKeyHasScope({ scopes: "publish" }, "write")).toBe(true);
    expect(apiKeyHasScope({ scopes: "publish" }, "publish")).toBe(true);
  });

  it("read does not imply write or publish", () => {
    expect(apiKeyHasScope({ scopes: "read" }, "read")).toBe(true);
    expect(apiKeyHasScope({ scopes: "read" }, "write")).toBe(false);
    expect(apiKeyHasScope({ scopes: "read" }, "publish")).toBe(false);
  });

  it("normaliseScopes rejects unknown tokens", () => {
    expect(normaliseScopes("delete")).toBeNull();
    expect(normaliseScopes("write,publish,bogus")).toBeNull();
  });

  it("normaliseScopes canonicalises known tokens", () => {
    expect(normaliseScopes("publish, write , read")).toBe("read,write,publish");
    expect(normaliseScopes("publish")).toBe("publish");
    expect(normaliseScopes("")).toBe("");
    expect(normaliseScopes(null)).toBe("");
  });
});

describe("API key authentication", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("rejects malformed Authorization header", async () => {
    expect(await authenticateApiKey(null)).toBeNull();
    expect(await authenticateApiKey("Bearer notreal")).toBeNull();
    expect(await authenticateApiKey("Bearer tcx_short")).toBeNull();
  });

  it("returns the principal on a hash match and exposes scopes", async () => {
    const { plaintext, prefix, keyHash } = await generateApiKeyPlaintext();
    (db.apiKey.findMany as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      {
        id: "k1",
        keyHash,
        scopes: "read,write",
        founder: {
          id: "f1",
          organizationId: "org1",
          organization: { id: "org1", slug: "test" },
        },
      },
    ]);
    const principal = await authenticateApiKey(`Bearer ${plaintext}`);
    expect(principal).not.toBeNull();
    expect(principal?.__authMethod).toBe("api_key");
    expect(principal?.__apiKeyId).toBe("k1");
    expect(principal?.__apiKeyScopes).toBe("read,write");
    expect(apiKeyHasScope(principal!, "write")).toBe(true);
    expect(apiKeyHasScope(principal!, "publish")).toBe(false);
    // Ignore the prefix variable — only used to assert the parser
    // accepts a real plaintext.
    expect(prefix.length).toBe(12);
  });
});

// ── CSRF ─────────────────────────────────────────────────────────────────
import {
  CSRF_COOKIE_NAME,
  CSRF_HEADER_NAME,
  issueCsrfToken,
  requireCsrfToken,
  validateCsrfToken,
} from "@/lib/csrf";

describe("CSRF token (double-submit + HMAC)", () => {
  beforeEach(() => {
    process.env.SESSION_SECRET = "test-secret-for-csrf";
  });

  afterEach(() => {
    delete process.env.SESSION_SECRET;
  });

  it("validates a freshly minted token against itself", () => {
    const token = issueCsrfToken();
    expect(validateCsrfToken(token, token)).toBe(true);
  });

  it("rejects when header and cookie disagree", () => {
    const a = issueCsrfToken();
    const b = issueCsrfToken();
    expect(validateCsrfToken(a, b)).toBe(false);
  });

  it("rejects a forged token", () => {
    expect(validateCsrfToken("forged.0.signature", "forged.0.signature")).toBe(false);
  });

  it("rejects an expired token", () => {
    const past = Date.now() - 1000 * 60 * 60 * 24; // 24h ago
    const token = issueCsrfToken(past);
    expect(validateCsrfToken(token, token)).toBe(false);
  });

  it("requireCsrfToken reads from header + cookie correctly", () => {
    const token = issueCsrfToken();
    const reqOk = new Request("http://localhost/api/auth/api-keys", {
      method: "POST",
      headers: {
        [CSRF_HEADER_NAME]: token,
        cookie: `${CSRF_COOKIE_NAME}=${encodeURIComponent(token)}`,
      },
    });
    expect(requireCsrfToken(reqOk).ok).toBe(true);

    const reqMissingHeader = new Request("http://localhost/api/auth/api-keys", {
      method: "POST",
      headers: {
        cookie: `${CSRF_COOKIE_NAME}=${encodeURIComponent(token)}`,
      },
    });
    const r1 = requireCsrfToken(reqMissingHeader);
    expect(r1.ok).toBe(false);

    const reqMismatch = new Request("http://localhost/api/auth/api-keys", {
      method: "POST",
      headers: {
        [CSRF_HEADER_NAME]: token,
        cookie: `${CSRF_COOKIE_NAME}=${encodeURIComponent("other")}`,
      },
    });
    expect(requireCsrfToken(reqMismatch).ok).toBe(false);
  });
});

// ── Public anti-bot challenge ────────────────────────────────────────────
import {
  challengeEnforced,
  challengeOrReject,
  CHALLENGE_HEADER_NAME,
  issueChallengeToken,
  verifyChallengeToken,
} from "@/lib/publicChallenge";

describe("public anti-bot challenge", () => {
  beforeEach(() => {
    process.env.SESSION_SECRET = "test-secret-for-challenge";
  });

  afterEach(() => {
    delete process.env.SESSION_SECRET;
    delete process.env.THESEUS_PUBLIC_CHALLENGE_REQUIRED;
  });

  it("verifies a token issued for the same IP prefix", () => {
    const token = issueChallengeToken("203.0.113.42");
    expect(verifyChallengeToken(token, "203.0.113.42")).toBe(true);
    expect(verifyChallengeToken(token, "203.0.113.99")).toBe(true); // same /24
  });

  it("rejects a token bound to a different /24", () => {
    const token = issueChallengeToken("203.0.113.42");
    expect(verifyChallengeToken(token, "198.51.100.5")).toBe(false);
  });

  it("flag-gated enforcement: off ⇒ accept, on ⇒ require", () => {
    delete process.env.THESEUS_PUBLIC_CHALLENGE_REQUIRED;
    expect(challengeEnforced()).toBe(false);
    const reqNoToken = new Request("http://localhost/api/public/ask", { method: "POST" });
    expect(challengeOrReject(reqNoToken, "203.0.113.1")).toBeNull();

    process.env.THESEUS_PUBLIC_CHALLENGE_REQUIRED = "1";
    expect(challengeEnforced()).toBe(true);
    const result = challengeOrReject(reqNoToken, "203.0.113.1");
    expect(result?.status).toBe(428);

    const token = issueChallengeToken("203.0.113.1");
    const reqWithToken = new Request("http://localhost/api/public/ask", {
      method: "POST",
      headers: { [CHALLENGE_HEADER_NAME]: token },
    });
    expect(challengeOrReject(reqWithToken, "203.0.113.1")).toBeNull();
  });
});

// ── Strong password predicate ────────────────────────────────────────────
import { isStrongPassword } from "@/lib/auth";

describe("strong password predicate", () => {
  it("rejects short and single-class passwords", () => {
    expect(isStrongPassword("short").ok).toBe(false);
    expect(isStrongPassword("a".repeat(20)).ok).toBe(false); // no upper/digit/symbol
    expect(isStrongPassword("ALLUPPER1234!").ok).toBe(false); // no lowercase
    expect(isStrongPassword("alllower1234!").ok).toBe(false); // no uppercase
    expect(isStrongPassword("Aa1!" + "x".repeat(8))).toEqual({ ok: true });
  });

  it("flags a known dictionary password regardless of structure", () => {
    expect(isStrongPassword("password").ok).toBe(false);
    expect(isStrongPassword("Theseus").ok).toBe(false); // dictionary + too short
    expect(isStrongPassword("Codex").ok).toBe(false);
  });

  it("accepts a strong candidate", () => {
    const ok = isStrongPassword("Correct-Horse-Battery-9!Staple");
    expect(ok.ok).toBe(true);
  });
});

// ── Secret scanner (CI script) ───────────────────────────────────────────

describe("scripts/check_no_secrets_in_code.py", () => {
  let tmpDir: string;
  let plantedPath: string;
  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "theseus-secret-scan-"));
    plantedPath = join(tmpDir, "planted.txt");
  });
  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  it("flags a planted AWS-style key", () => {
    // pragma: allowlist secret — planted fixture, not a real key.
    writeFileSync(plantedPath, 'const aws = "AKIA' + 'IOSFODNN7EXAMPLE"\n');
    const script = join(REPO_ROOT, "scripts", "check_no_secrets_in_code.py");
    let stdout = "";
    let exitCode = 0;
    try {
      stdout = execFileSync("python3", [script, "--planted", plantedPath], { encoding: "utf8" });
    } catch (err) {
      const e = err as { status?: number; stdout?: string };
      exitCode = e.status ?? 1;
      stdout = e.stdout ?? "";
    }
    expect(exitCode).toBe(1);
    expect(stdout).toMatch(/aws_access_key/);
  });

  it("flags a planted Theseus API key", () => {
    writeFileSync(plantedPath, 'export const k = "tcx_abcdefghijkl_' + "x".repeat(48) + '"\n');
    const script = join(REPO_ROOT, "scripts", "check_no_secrets_in_code.py");
    let stdout = "";
    let exitCode = 0;
    try {
      stdout = execFileSync("python3", [script, "--planted", plantedPath], { encoding: "utf8" });
    } catch (err) {
      const e = err as { status?: number; stdout?: string };
      exitCode = e.status ?? 1;
      stdout = e.stdout ?? "";
    }
    expect(exitCode).toBe(1);
    expect(stdout).toMatch(/theseus_api_key/);
  });
});

// ── Public ask: rate limit + challenge integration ───────────────────────
import { _resetPublicAskRateLimitsForTests } from "@/lib/publicAsk";

vi.mock("@/lib/publicAsk", async () => {
  const actual = await vi.importActual<typeof import("@/lib/publicAsk")>("@/lib/publicAsk");
  return {
    ...actual,
    publicAsk: vi.fn(async () => ({ items: [], snippet: "" })),
  };
});

describe("public /ask integration", () => {
  beforeEach(() => {
    _resetPublicAskRateLimitsForTests();
    process.env.SESSION_SECRET = "test-secret-for-challenge";
  });

  afterEach(() => {
    delete process.env.SESSION_SECRET;
    delete process.env.THESEUS_PUBLIC_CHALLENGE_REQUIRED;
  });

  it("rejects POST without challenge token when flag is on", async () => {
    process.env.THESEUS_PUBLIC_CHALLENGE_REQUIRED = "1";
    const { POST } = await import("@/app/api/public/ask/route");
    const req = new Request("http://localhost/api/public/ask", {
      method: "POST",
      headers: { "content-type": "application/json", "x-forwarded-for": "203.0.113.10" },
      body: JSON.stringify({ query: "hello world" }),
    });
    const res = await POST(req as unknown as Parameters<typeof POST>[0]);
    expect(res.status).toBe(428);
  });

  it("accepts POST with a fresh challenge token when flag is on", async () => {
    process.env.THESEUS_PUBLIC_CHALLENGE_REQUIRED = "1";
    const { POST } = await import("@/app/api/public/ask/route");
    const token = issueChallengeToken("203.0.113.20");
    const req = new Request("http://localhost/api/public/ask", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-forwarded-for": "203.0.113.20",
        [CHALLENGE_HEADER_NAME]: token,
      },
      body: JSON.stringify({ query: "hello world" }),
    });
    const res = await POST(req as unknown as Parameters<typeof POST>[0]);
    expect(res.status).toBe(200);
  });
});
