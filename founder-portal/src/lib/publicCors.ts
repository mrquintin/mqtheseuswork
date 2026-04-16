import type { NextRequest } from "next/server";

/**
 * CORS for unauthenticated public write endpoints (e.g. structured responses).
 * Comma-separated `THESEUS_PUBLIC_CORS_ORIGINS`; default `*` (dev only).
 */
export function publicCorsHeaders(req: NextRequest): HeadersInit {
  const allowed =
    process.env.THESEUS_PUBLIC_CORS_ORIGINS?.split(",").map((s) => s.trim()).filter(Boolean) ?? [];
  const origin = req.headers.get("origin") ?? "";
  const allowAll = allowed.length === 0 || allowed.includes("*");
  const allow =
    allowAll ? "*" : allowed.includes(origin) ? origin : allowed[0] === "*" ? "*" : allowed[0] ?? "*";
  const headers: Record<string, string> = {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    Vary: "Origin",
  };
  if (allow !== "*") {
    headers["Access-Control-Allow-Credentials"] = "true";
  }
  return headers;
}
