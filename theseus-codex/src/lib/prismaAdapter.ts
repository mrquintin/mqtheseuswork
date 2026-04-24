import { PrismaPg } from "@prisma/adapter-pg";

/**
 * Prisma 7+ driver adapter. We're on Postgres everywhere (Supabase / Neon /
 * local Docker), so this just constructs a pg pool from `DATABASE_URL`.
 *
 * Expected URLs:
 *   - Supabase pooler:  postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:6543/postgres?pgbouncer=true
 *   - Supabase direct:  postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres
 *   - Neon:             postgresql://<user>:<pw>@<project>-pooler.<region>.aws.neon.tech/<db>?sslmode=require
 *   - Local Docker:     postgresql://theseus:theseus@localhost:5432/theseus
 *
 * For serverless (Vercel), prefer the pooled/pgbouncer URL so connection
 * churn doesn't exhaust Postgres slots.
 *
 * Validation note: we pre-validate with `new URL()` before handing the
 * string to PrismaPg. Two reasons:
 *
 *   1. Prisma 7 throws ERR_INVALID_URL deep inside the engine if the URL
 *      has stray whitespace, an unescaped character in the password, or
 *      a missing component. The user-visible message you get is just
 *      "Invalid URL" with a wrapped PrismaClientKnownRequestError —
 *      unrecoverably unclear about WHICH url. Doing the parse here means
 *      we can print a masked version so the caller can see exactly what
 *      string we tried to use.
 *
 *   2. Shell-exported URLs occasionally pick up a trailing newline (copy
 *      from a multi-line source, pasted into `export X=…`), which Node's
 *      URL parser rejects. Trimming up-front eliminates this whole class
 *      of confusing failures.
 */

function maskUrl(url: string): string {
  // Hide the password — keep everything else visible so the user can see
  // whether the protocol, username, host, port, and path look right.
  try {
    const u = new URL(url);
    if (u.password) u.password = "***";
    return u.toString();
  } catch {
    return url.replace(/:[^@/]+@/, ":***@");
  }
}

export function createSqlAdapter() {
  const raw = process.env.DATABASE_URL;
  if (!raw) {
    throw new Error(
      "DATABASE_URL is not set. See theseus-codex/.env.example. " +
        "For local scripts, export it first, e.g.\n" +
        '  export DATABASE_URL="postgresql://user:pass@host:5432/db"',
    );
  }

  // Trim stray whitespace/newlines before any validation. A URL copied
  // from a multi-line source and dropped into `export X=...` on the
  // shell quite often picks up an invisible \n or trailing space, and
  // Node's `new URL()` rejects those with ERR_INVALID_URL.
  const url = raw.trim();

  if (!url.startsWith("postgres:") && !url.startsWith("postgresql:")) {
    throw new Error(
      `DATABASE_URL must be a Postgres URL — got a value starting with "${url.slice(0, 16)}…".\n` +
        "SQLite support was dropped when the Codex moved to cloud hosting; " +
        "see docs/Operations_Manual.md for local-dev Postgres setup.",
    );
  }

  // Pre-validate. If this throws, bubble up a message that says exactly
  // which URL failed (masked) and what Node said, so the caller doesn't
  // have to hunt through a 20-line Prisma stack for "Invalid URL".
  try {
    // eslint-disable-next-line no-new
    new URL(url);
  } catch (e) {
    const reason = e instanceof Error ? e.message : String(e);
    throw new Error(
      `DATABASE_URL is not a valid URL (Node says: ${reason}).\n` +
        `Value (password masked): ${maskUrl(url)}\n` +
        "Common causes:\n" +
        "  • A trailing newline or space in the shell export (retype it in one line).\n" +
        "  • Unescaped special characters in the password (percent-encode :, /, ?, #, @, space).\n" +
        "  • The entire password has been lost, leaving `user:@host`.",
    );
  }

  return new PrismaPg({ connectionString: url });
}
