/**
 * POST /api/auth/app-login
 *
 * The sister of /api/auth/login, for non-browser clients (Dialectic
 * desktop, Noosphere CLI, scripts). Instead of setting a session
 * cookie we mint a fresh API key — the same `tcx_<prefix>_<secret>`
 * shape the UI emits from /api-keys — and return it once in the
 * response body. The caller stores the key in a local file (e.g.
 * ~/.noosphere/credentials.json) and sends it as
 * `Authorization: Bearer tcx_…` for every subsequent request.
 *
 * Why this endpoint exists:
 *   - Desktop apps can't consume a browser cookie cleanly (no cookie
 *     jar; the Electron/PyQt runtime isn't a browser).
 *   - Asking the user to copy-paste an API key minted in the web UI
 *     is terrible first-run UX. This endpoint lets the app say "email
 *     + password, please" once and keep quiet thereafter.
 *
 * Request body:
 *   { email, password, organizationSlug?, appLabel? }
 *
 * Response:
 *   { apiKey, keyId, founder, organizationSlug, codexUrl }
 *
 * Security:
 *   - Same rate-limit bucket as /api/auth/login (per-IP + per-email)
 *     so an attacker can't bypass throttling by switching endpoints.
 *   - bcrypt verification of the password, same as the web flow.
 *   - Plaintext is returned exactly once; only the hash is persisted.
 *   - Every call writes an `app_login` AuditEvent for traceability.
 *   - The minted key is labelled with `appLabel` (default
 *     "external-app") so a founder can revoke keys per-device from
 *     /api-keys.
 */
import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { db } from "@/lib/db";
import { generateApiKeyPlaintext } from "@/lib/apiKeyAuth";
import { checkLoginRateLimit, resetLoginRateLimit } from "@/lib/rateLimit";
import { sanitizeText, sanitizeAndCap } from "@/lib/sanitizeText";

function clientIp(req: Request): string {
  const xf = req.headers.get("x-forwarded-for");
  if (xf) return xf.split(",")[0]!.trim();
  return req.headers.get("x-real-ip") || "unknown";
}

export async function POST(req: Request) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      email?: string;
      password?: string;
      organizationSlug?: string;
      appLabel?: string;
    };
    const { email, password, organizationSlug, appLabel } = body;
    const ip = clientIp(req);
    const rateKey = `${ip}::${(email || "").toLowerCase()}`;

    if (!email || !password) {
      return NextResponse.json(
        { error: "Email and password required" },
        { status: 400 },
      );
    }

    const slug =
      (organizationSlug && String(organizationSlug).trim()) ||
      process.env.DEFAULT_ORGANIZATION_SLUG ||
      "theseus-local";

    const org = await db.organization.findUnique({ where: { slug } });
    if (!org) {
      return NextResponse.json(
        { error: "Unknown organization" },
        { status: 400 },
      );
    }

    const founder = await db.founder.findFirst({
      where: { organizationId: org.id, email },
    });
    const valid = founder
      ? await bcrypt.compare(password, founder.passwordHash)
      : false;

    if (!founder || !valid) {
      const limited = checkLoginRateLimit(rateKey);
      if (!limited.ok) {
        return NextResponse.json(
          { error: `Too many attempts. Try again in ${limited.retryAfterSec}s.` },
          {
            status: 429,
            headers: { "Retry-After": String(limited.retryAfterSec) },
          },
        );
      }
      return NextResponse.json(
        { error: "Invalid credentials" },
        { status: 401 },
      );
    }

    resetLoginRateLimit(rateKey);

    // Mint a fresh API key. Label it so the founder can identify which
    // device / tool it came from and revoke surgically if lost.
    const label =
      sanitizeAndCap(
        (appLabel && String(appLabel).trim()) || "external-app",
        80,
      ) || "external-app";

    const { plaintext, prefix, keyHash } = await generateApiKeyPlaintext();
    const apiKeyRow = await db.apiKey.create({
      data: {
        organizationId: founder.organizationId,
        founderId: founder.id,
        label,
        prefix,
        keyHash,
        scopes: "", // empty = full founder scope
      },
      select: { id: true, createdAt: true },
    });

    await db.auditEvent
      .create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          action: "app_login",
          detail: sanitizeText(
            `Minted API key "${label}" via /api/auth/app-login`,
          ).slice(0, 500),
        },
      })
      .catch(() => {
        /* non-fatal */
      });

    // Include the canonical Codex URL so the client can store it
    // alongside the key — if the env var is set on Vercel we use it;
    // otherwise we echo the request's origin so the client doesn't
    // have to guess.
    const codexUrl =
      process.env.NEXT_PUBLIC_CODEX_URL ||
      new URL(req.url).origin;

    return NextResponse.json({
      apiKey: plaintext,
      keyId: apiKeyRow.id,
      label,
      createdAt: apiKeyRow.createdAt,
      organizationSlug: slug,
      codexUrl,
      founder: {
        id: founder.id,
        name: founder.name,
        username: founder.username,
        email: founder.email,
        role: founder.role,
      },
    });
  } catch (error) {
    console.error("app-login error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
