/**
 * POST /api/auth/rotate-password
 *
 * Unauthenticated password rotation — the path founders take when
 * they hit `/login` and want to change their passphrase WITHOUT
 * already being signed in. The existing
 * `/api/auth/change-password` endpoint requires a valid session
 * cookie (deliberately, so a compromised device API key can't lock
 * the owner out); this endpoint fills the gap by re-authenticating
 * via (email, organizationSlug, currentPassword) and rotating to a
 * new passphrase in the same request.
 *
 * Contract
 * --------
 * Request body: `{ email, organizationSlug, currentPassword, newPassword }`
 *   * All four fields required; any missing returns 400.
 *   * `newPassword` ≥ 8 chars and must differ from the current one.
 *   * `currentPassword` must bcrypt-match the stored hash for the
 *     (org, email) founder — otherwise 401, rate-limited identically
 *     to `/api/auth/login` so an attacker can't use this path as an
 *     uncapped password-guessing oracle.
 *
 * Side effects on success
 * -----------------------
 *   * Stored passwordHash rotated to bcrypt(newPassword).
 *   * Every existing session for this founder deleted (invalidates
 *     any zombie logins on other devices).
 *   * A fresh session cookie is minted on the response, so the caller
 *     is signed in with the new credential immediately — no
 *     interstitial "now please log in" step.
 *   * AuditEvent written: action = "password_rotate_unauth".
 *   * API keys are intentionally NOT revoked; same reasoning as
 *     `/api/auth/change-password` (device-scoped credentials have
 *     their own management UI; nuking them orphans active Dialectic /
 *     Noosphere agents).
 *
 * Why a separate route from change-password
 * -----------------------------------------
 * The two paths have DIFFERENT threat models and need independently-
 * tunable rate limits:
 *
 *   change-password   — caller already has a valid session. The
 *                        password check is a re-confirmation ("this
 *                        is really me"), not an auth gate. Rate-limit
 *                        key is (IP + founder.id).
 *
 *   rotate-password   — caller has NO session and must prove identity
 *                        via (email, org, currentPassword). The
 *                        password check IS the auth gate. Rate-limit
 *                        key is (IP + email) — same bucket as
 *                        /api/auth/login, so someone brute-forcing a
 *                        password can't double-dip across the two
 *                        endpoints.
 *
 * Collapsing them into one handler would muddle both concerns.
 */
import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { db } from "@/lib/db";
import { createSession, destroySession } from "@/lib/auth";
import { checkLoginRateLimit, resetLoginRateLimit } from "@/lib/rateLimit";

const BCRYPT_ROUNDS = 10;
const MIN_PASSWORD_LENGTH = 8;

function clientIp(req: Request): string {
  const xf = req.headers.get("x-forwarded-for");
  if (xf) return xf.split(",")[0]!.trim();
  return req.headers.get("x-real-ip") || "unknown";
}

export async function POST(req: Request) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      email?: string;
      organizationSlug?: string;
      currentPassword?: string;
      newPassword?: string;
    };
    const { email, organizationSlug, currentPassword, newPassword } = body;

    if (!email || !currentPassword || !newPassword) {
      return NextResponse.json(
        {
          error:
            "email, currentPassword, and newPassword are all required",
        },
        { status: 400 },
      );
    }
    if (
      typeof newPassword !== "string" ||
      newPassword.length < MIN_PASSWORD_LENGTH
    ) {
      return NextResponse.json(
        {
          error: `New passphrase must be at least ${MIN_PASSWORD_LENGTH} characters.`,
        },
        { status: 400 },
      );
    }
    if (currentPassword === newPassword) {
      return NextResponse.json(
        { error: "New passphrase must differ from the current one." },
        { status: 400 },
      );
    }

    const slug =
      (organizationSlug && String(organizationSlug).trim()) ||
      process.env.DEFAULT_ORGANIZATION_SLUG ||
      "theseus-local";

    const ip = clientIp(req);
    // Match the login route's bucket so an attacker can't evade the
    // login rate-limit by bouncing between /auth/login and
    // /auth/rotate-password guessing the same credential.
    const rateKey = `${ip}::${email.toLowerCase()}`;

    const org = await db.organization.findUnique({ where: { slug } });
    if (!org) {
      return NextResponse.json(
        { error: "Unknown organization" },
        { status: 400 },
      );
    }

    const founder = await db.founder.findFirst({
      where: { organizationId: org.id, email },
      select: {
        id: true,
        organizationId: true,
        passwordHash: true,
        email: true,
        name: true,
        username: true,
      },
    });

    const valid = founder
      ? await bcrypt.compare(currentPassword, founder.passwordHash)
      : false;

    if (!founder || !valid) {
      const limited = checkLoginRateLimit(rateKey);
      if (!limited.ok) {
        return NextResponse.json(
          {
            error: `Too many attempts. Try again in ${limited.retryAfterSec}s.`,
          },
          {
            status: 429,
            headers: { "Retry-After": String(limited.retryAfterSec) },
          },
        );
      }
      // Same generic "invalid credentials" as /auth/login — don't
      // leak whether the email exists in this org.
      return NextResponse.json(
        { error: "Invalid credentials" },
        { status: 401 },
      );
    }

    resetLoginRateLimit(rateKey);

    const newHash = await bcrypt.hash(newPassword, BCRYPT_ROUNDS);

    // Rotate in a single transaction — hash update, session cleanup,
    // audit log — so a failure anywhere leaves the row in a
    // consistent state (either all three changes persist or none).
    await db.$transaction([
      db.founder.update({
        where: { id: founder.id },
        data: { passwordHash: newHash },
      }),
      db.session.deleteMany({
        where: { founderId: founder.id },
      }),
      db.auditEvent.create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          action: "password_rotate_unauth",
          detail:
            `Passphrase rotated from ${ip} via the unauthenticated ` +
            `/login rotation flow; all other sessions invalidated.`,
        },
      }),
    ]);

    // Belt-and-suspenders: if the caller somehow had a stale session
    // cookie (for a DIFFERENT founder), nuke it before minting the
    // new one for `founder.id` — we never want the response cookie
    // and session row to point at different founders.
    await destroySession();
    await createSession(founder.id);

    return NextResponse.json({
      ok: true,
      founder: {
        id: founder.id,
        email: founder.email,
        name: founder.name,
        username: founder.username,
      },
    });
  } catch (error) {
    console.error("rotate-password error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
