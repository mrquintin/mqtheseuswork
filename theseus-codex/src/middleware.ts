import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** Must match `COOKIE_NAME` in `src/lib/auth.ts` (middleware stays Edge-safe: no Node crypto). */
const SESSION_COOKIE = "theseus_session";

/** Must match `CSRF_COOKIE_NAME` in `src/lib/csrf.ts`. The middleware
 *  issues this cookie *only* via Edge-safe Web Crypto so we don't pull
 *  in `node:crypto` here. The cookie is a random nonce; the
 *  state-changing route handler is what HMAC-validates it via
 *  `src/lib/csrf.ts` on POST/PATCH/DELETE. */
const CSRF_COOKIE = "theseus_csrf";

const PROTECTED_PREFIXES = [
  "/dashboard",
  "/upload",
  "/founders",
  "/conclusions",
  "/contradictions",
  "/research",
  "/open-questions",
  "/publication",
  "/library",
  "/account",
  "/forecasts/operator",
  "/q/",
];

async function edgeIssueCsrfToken(secret: string, now: number): Promise<string> {
  const nonceBytes = new Uint8Array(18);
  crypto.getRandomValues(nonceBytes);
  const nonce = b64url(nonceBytes);
  const exp = now + 12 * 60 * 60 * 1000;
  const payload = `${nonce}.${exp}`;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = new Uint8Array(
    await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload)),
  );
  return `${payload}.${b64url(sig)}`;
}

function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function csrfSecret(): string | null {
  const s = process.env.SESSION_SECRET;
  if (!s || s === "change-me-to-a-random-hex-string") {
    if (process.env.NODE_ENV === "production") return null;
    return "dev-insecure-csrf-secret-do-not-use";
  }
  return s;
}

/**
 * Lightweight gate: signed cookie is `payload.signature` (two segments).
 * Full signature + DB validation runs in server components / route handlers.
 *
 * Also: on any authenticated request that lacks a CSRF cookie, mint
 * one. The cookie is `SameSite=Lax`, *not* `HttpOnly` (the client
 * needs to read it to copy into the `X-CSRF-Token` header on
 * mutating requests). The session cookie itself is the credential;
 * the CSRF cookie is purely a defence-in-depth nonce.
 */
export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const needsAuth = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  if (!needsAuth) {
    return NextResponse.next();
  }

  const raw = request.cookies.get(SESSION_COOKIE)?.value;
  if (!raw || !raw.includes(".")) {
    // Redirect unauthenticated requests to the login page. The Gate
    // lives at `/login` now; `/` hosts the public blog and no longer
    // has the sign-in form. The original path is preserved as `?next=`
    // so we can send the user to where they were heading after they
    // sign in.
    const gate = new URL("/login", request.url);
    gate.searchParams.set("next", pathname);
    return NextResponse.redirect(gate);
  }

  const response = NextResponse.next();
  const existingCsrf = request.cookies.get(CSRF_COOKIE)?.value;
  if (!existingCsrf) {
    const secret = csrfSecret();
    if (secret) {
      try {
        const token = await edgeIssueCsrfToken(secret, Date.now());
        response.cookies.set(CSRF_COOKIE, token, {
          httpOnly: false,
          secure: process.env.NODE_ENV === "production",
          sameSite: "lax",
          path: "/",
          maxAge: 12 * 60 * 60,
        });
      } catch {
        // Non-fatal: client will retry on the next protected GET.
      }
    }
  }
  return response;
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/upload/:path*",
    "/founders/:path*",
    "/conclusions/:path*",
    "/contradictions/:path*",
    "/research/:path*",
    "/open-questions/:path*",
    "/publication/:path*",
    "/library/:path*",
    "/account/:path*",
    "/forecasts/operator/:path*",
    "/q/:path*",
  ],
};
