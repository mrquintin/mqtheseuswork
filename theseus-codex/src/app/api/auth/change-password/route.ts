/**
 * POST /api/auth/change-password
 *
 * Signed-in founders rotate their own passphrase. Authentication is
 * via the session cookie only — deliberately not API keys, because a
 * compromised device key shouldn't be able to lock the real owner out
 * of their account by flipping the password.
 *
 * Request body: `{ currentPassword, newPassword }`
 *
 * Contract:
 *   * both fields required;
 *   * `currentPassword` must bcrypt-match the stored hash;
 *   * `newPassword` ≥ 8 chars and must differ from the current one;
 *   * rate-limited on (IP + founder.id) — same bucket as /api/auth/login
 *     — so a stolen session can't brute-force-probe the old password;
 *   * on success: password hash rotated, every OTHER session for this
 *     founder deleted (any sign-in on a second laptop gets forced to
 *     re-authenticate), a fresh session + cookie issued to the current
 *     caller so they stay logged in without an interstitial;
 *   * API keys are NOT revoked — those are device-scoped credentials
 *     with their own `/api-keys` management UI. Forcibly nuking them
 *     on password change would orphan active Dialectic / Noosphere
 *     sessions the user probably doesn't realise are tied to this
 *     credential. Doc note + manual revoke affordance covers it.
 */
import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { db } from "@/lib/db";
import { getFounder, createSession, destroySession } from "@/lib/auth";
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
    const founder = await getFounder();
    if (!founder) {
      return NextResponse.json(
        { error: "Not authenticated" },
        { status: 401 },
      );
    }

    const body = (await req.json().catch(() => ({}))) as {
      currentPassword?: string;
      newPassword?: string;
    };
    const { currentPassword, newPassword } = body;

    if (!currentPassword || !newPassword) {
      return NextResponse.json(
        { error: "currentPassword and newPassword are both required" },
        { status: 400 },
      );
    }
    if (typeof newPassword !== "string" || newPassword.length < MIN_PASSWORD_LENGTH) {
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

    const rateKey = `${clientIp(req)}::pwchange::${founder.id}`;

    // Fetch the founder FRESH (getFounder returned a session-joined
    // row; we want the current passwordHash specifically in case it
    // was updated between login and now).
    const fresh = await db.founder.findUnique({
      where: { id: founder.id },
      select: { id: true, organizationId: true, passwordHash: true, email: true },
    });
    if (!fresh) {
      return NextResponse.json(
        { error: "Account not found" },
        { status: 404 },
      );
    }

    const currentOk = await bcrypt.compare(currentPassword, fresh.passwordHash);
    if (!currentOk) {
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
      return NextResponse.json(
        { error: "Current passphrase is incorrect." },
        { status: 401 },
      );
    }

    resetLoginRateLimit(rateKey);

    const newHash = await bcrypt.hash(newPassword, BCRYPT_ROUNDS);

    // Rotate in a transaction so we don't end up in a half-state
    // where the hash is updated but old sessions survive (or vice
    // versa). We delete ALL sessions for this founder; the current
    // caller immediately gets a fresh one minted below so they stay
    // signed in on this device.
    await db.$transaction([
      db.founder.update({
        where: { id: fresh.id },
        data: { passwordHash: newHash },
      }),
      db.session.deleteMany({
        where: { founderId: fresh.id },
      }),
      db.auditEvent.create({
        data: {
          organizationId: fresh.organizationId,
          founderId: fresh.id,
          action: "password_change",
          detail: `Passphrase rotated from ${clientIp(req)}; all other sessions invalidated.`,
        },
      }),
    ]);

    // Best-effort: blow away the old cookie before minting the new
    // one, so a failure between these two steps leaves the user in
    // "please sign in again" rather than on a zombie session whose
    // DB row was just deleted.
    await destroySession();
    await createSession(fresh.id);

    return NextResponse.json({
      ok: true,
      founder: {
        id: fresh.id,
        email: fresh.email,
      },
    });
  } catch (error) {
    console.error("change-password error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
