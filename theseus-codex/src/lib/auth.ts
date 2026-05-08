import { createHmac, randomBytes, timingSafeEqual } from "crypto";
import { cookies } from "next/headers";
import { db } from "./db";

/** Exported for documentation; middleware uses the same literal (Edge-safe, no Node crypto). */
export const THESEUS_SESSION_COOKIE = "theseus_session";
const COOKIE_NAME = THESEUS_SESSION_COOKIE;

function getSessionSecret(): string {
  const s = process.env.SESSION_SECRET;
  if (!s || s === "change-me-to-a-random-hex-string") {
    if (process.env.NODE_ENV === "production") {
      throw new Error("SESSION_SECRET must be set in production");
    }
    return "dev-insecure-session-secret-do-not-use";
  }
  return s;
}

/** Base64url encode */
function b64url(buf: Buffer): string {
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function signPayload(payloadJson: string): string {
  const secret = getSessionSecret();
  const sig = createHmac("sha256", secret).update(payloadJson).digest();
  return `${b64url(Buffer.from(payloadJson, "utf8"))}.${b64url(sig)}`;
}

/**
 * Verify signed session cookie (Edge-safe string compare; crypto in Node).
 * Returns `{ token, exp }` from payload or null.
 */
export function verifySessionCookieValue(raw: string | undefined): {
  token: string;
  exp: number;
} | null {
  if (!raw || !raw.includes(".")) return null;
  const lastDot = raw.lastIndexOf(".");
  const payloadB64 = raw.slice(0, lastDot);
  const sigB64 = raw.slice(lastDot + 1);
  try {
    const payloadJson = Buffer.from(
      payloadB64.replace(/-/g, "+").replace(/_/g, "/"),
      "base64",
    ).toString("utf8");
    const expectedSig = createHmac("sha256", getSessionSecret())
      .update(payloadJson)
      .digest();
    const gotSig = Buffer.from(
      sigB64.replace(/-/g, "+").replace(/_/g, "/"),
      "base64",
    );
    if (gotSig.length !== expectedSig.length || !timingSafeEqual(gotSig, expectedSig)) {
      return null;
    }
    const body = JSON.parse(payloadJson) as { t: string; e: number };
    if (!body.t || typeof body.e !== "number") return null;
    return { token: body.t, exp: body.e };
  } catch {
    return null;
  }
}

/**
 * Get the currently authenticated founder from the signed HTTP-only session cookie.
 */
export async function getFounder() {
  const cookieStore = await cookies();
  const raw = cookieStore.get(COOKIE_NAME)?.value;
  const v = verifySessionCookieValue(raw);
  if (!v) return null;
  if (Date.now() > v.exp) return null;

  const session = await db.session.findUnique({
    where: { token: v.token },
    include: { founder: { include: { organization: true } } },
  });

  if (!session || session.expiresAt < new Date()) {
    return null;
  }

  return session.founder;
}

/**
 * Create a DB session and set signed HTTP-only cookie.
 */
export async function createSession(founderId: string) {
  const token = randomBytes(32).toString("hex");
  const expiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);

  const f = await db.founder.findUnique({
    where: { id: founderId },
    select: { organizationId: true },
  });
  if (!f) {
    throw new Error("createSession: founder not found");
  }

  await db.session.create({
    data: {
      organizationId: f.organizationId,
      founderId,
      token,
      expiresAt,
    },
  });

  const payload = JSON.stringify({ t: token, e: expiresAt.getTime() });
  const signed = signPayload(payload);

  const cookieStore = await cookies();
  cookieStore.set(COOKIE_NAME, signed, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    expires: expiresAt,
    path: "/",
  });

  return token;
}

export async function destroySession() {
  const cookieStore = await cookies();
  const raw = cookieStore.get(COOKIE_NAME)?.value;
  const v = verifySessionCookieValue(raw);
  if (v?.token) {
    await db.session.deleteMany({ where: { token: v.token } });
  }
  cookieStore.delete(COOKIE_NAME);
}

export { COOKIE_NAME };

// ── Password strength predicate ─────────────────────────────────────────────
//
// Founder login is the firm's identity gate; a guessable passphrase
// here is the difference between "an attacker reads the dashboard"
// and "an attacker publishes under our signature". Threshold is set
// from the threat model (`docs/security/Threat_Model.md` §5).

const COMMON_PASSWORDS: ReadonlySet<string> = new Set([
  "password",
  "password1",
  "password123",
  "letmein",
  "welcome",
  "admin",
  "administrator",
  "qwerty",
  "qwerty123",
  "iloveyou",
  "abc123",
  "12345678",
  "123456789",
  "1234567890",
  "111111",
  "monkey",
  "dragon",
  "master",
  "sunshine",
  "princess",
  "shadow",
  "football",
  "baseball",
  "trustno1",
  "passw0rd",
  "p@ssword",
  "p@ssw0rd",
  "qazwsx",
  "qwertyuiop",
  "michael",
  "ashley",
  "111222",
  "654321",
  "123123",
  "000000",
  "letmein123",
  "starwars",
  "freedom",
  "whatever",
  "hello",
  "hello123",
  "welcome1",
  "summer",
  "winter",
  "spring",
  "autumn",
  "theseus",
  "founder",
  "noosphere",
  "currents",
  "codex",
]);

export type PasswordCheck =
  | { ok: true }
  | { ok: false; reason: string };

/**
 * Strong-password predicate for the password-set/change handlers.
 *
 * Rules (intentionally explicit so the UI can mirror them):
 *   - ≥ 12 characters
 *   - at least one lowercase, one uppercase, one digit
 *   - at least one non-alphanumeric character
 *   - not in the small dictionary above
 *
 * Returns a structured result so the form can render the *specific*
 * rule the candidate violated rather than a generic "too weak".
 */
export function isStrongPassword(candidate: string): PasswordCheck {
  if (typeof candidate !== "string") return { ok: false, reason: "Password must be a string." };
  if (candidate.length < 12) {
    return { ok: false, reason: "Password must be at least 12 characters." };
  }
  if (candidate.length > 1024) {
    return { ok: false, reason: "Password is unreasonably long." };
  }
  if (!/[a-z]/.test(candidate)) {
    return { ok: false, reason: "Password must contain a lowercase letter." };
  }
  if (!/[A-Z]/.test(candidate)) {
    return { ok: false, reason: "Password must contain an uppercase letter." };
  }
  if (!/[0-9]/.test(candidate)) {
    return { ok: false, reason: "Password must contain a digit." };
  }
  if (!/[^A-Za-z0-9]/.test(candidate)) {
    return { ok: false, reason: "Password must contain a punctuation or symbol character." };
  }
  if (COMMON_PASSWORDS.has(candidate.toLowerCase())) {
    return { ok: false, reason: "Password appears in the common-password dictionary." };
  }
  return { ok: true };
}

