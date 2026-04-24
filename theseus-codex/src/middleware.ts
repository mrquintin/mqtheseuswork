import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** Must match `COOKIE_NAME` in `src/lib/auth.ts` (middleware stays Edge-safe: no Node crypto). */
const SESSION_COOKIE = "theseus_session";

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
  "/q/",
];

/**
 * Lightweight gate: signed cookie is `payload.signature` (two segments).
 * Full signature + DB validation runs in server components / route handlers.
 */
export function middleware(request: NextRequest) {
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

  return NextResponse.next();
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
    "/q/:path*",
  ],
};
