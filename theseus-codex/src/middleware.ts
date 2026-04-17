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
    const login = new URL("/login", request.url);
    login.searchParams.set("next", pathname);
    return NextResponse.redirect(login);
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
    "/q/:path*",
  ],
};
