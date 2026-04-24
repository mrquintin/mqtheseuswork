/**
 * Wipe the Codex "library" — everything the UI surfaces on the Dashboard,
 * Conclusions, Review, Contradictions, Open Questions, Drift Events,
 * Research Suggestions, Publication Reviews, Published Conclusions, Public
 * Responses, Uploads, and AuditEvents pages — so you can start from a
 * genuinely empty state.
 *
 * DOES NOT delete:
 *   - Organization rows
 *   - Founder rows (your login accounts)
 *   - ApiKey rows (Dialectic auto-sync credentials)
 *   - Session rows (active browser sessions; optional, flag-gated)
 *
 * Usage:
 *   cd theseus-codex
 *   DATABASE_URL="<your Supabase DIRECT_URL>" \
 *     npx tsx scripts/clear-library.ts
 *
 * Flags (all optional, space-separated after the command):
 *   --also-sessions   also invalidate browser sessions (forces re-login)
 *   --keep-audit      retain the AuditEvent trail (default: wipe it too)
 *   --dry-run         print counts only; make no changes
 *   --yes             skip the interactive confirmation prompt
 *
 * Tables are deleted in dependency order so foreign-key cascades never bite.
 * The script also disconnects at the end so `tsx` exits cleanly even when
 * the Postgres connection has lingering idle transactions from the pool.
 */

import { PrismaClient } from "@prisma/client";
import * as readline from "readline";
import { createSqlAdapter } from "../src/lib/prismaAdapter";

if (!process.env.DATABASE_URL) {
  console.error(
    "DATABASE_URL is required. Point it at your Supabase DIRECT_URL (port 5432, not the pooler).",
  );
  process.exit(1);
}

// Preflight: trim + parse + mask the URL, and print what we're about to
// use. If the URL was munged anywhere between the shell export and here
// (stray newline, lost escape, dotenv override), this banner makes it
// obvious before Prisma throws a cryptic `ERR_INVALID_URL`.
{
  const raw = process.env.DATABASE_URL;
  const trimmed = raw.trim();
  if (trimmed !== raw) {
    console.log(
      "[preflight] Stripped trailing whitespace/newline from DATABASE_URL.",
    );
    process.env.DATABASE_URL = trimmed;
  }
  try {
    const u = new URL(trimmed);
    const masked = new URL(trimmed);
    if (masked.password) masked.password = "***";
    console.log(`[preflight] DATABASE_URL: ${masked.toString()}`);
    console.log(
      `[preflight] Host: ${u.host}  User: ${u.username}  DB: ${u.pathname.replace(/^\//, "")}`,
    );
  } catch (e) {
    console.error(
      `[preflight] DATABASE_URL failed URL parsing: ${e instanceof Error ? e.message : String(e)}`,
    );
    console.error(
      "           Most common cause: a trailing newline in `export DATABASE_URL=…`.",
    );
    console.error("           Retype the export on one line and try again.");
    process.exit(1);
  }
}

const flags = new Set(process.argv.slice(2));
const DRY_RUN = flags.has("--dry-run");
const ALSO_SESSIONS = flags.has("--also-sessions");
const KEEP_AUDIT = flags.has("--keep-audit");
const AUTO_YES = flags.has("--yes");

const db = new PrismaClient({ adapter: createSqlAdapter() });

async function prompt(question: string): Promise<boolean> {
  if (AUTO_YES) return true;
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim().toLowerCase().startsWith("y"));
    });
  });
}

interface Counts {
  [table: string]: number;
}

async function tally(): Promise<Counts> {
  const [
    upload,
    conclusion,
    publicationReview,
    publishedConclusion,
    publicResponse,
    contradiction,
    driftEvent,
    researchSuggestion,
    reviewItem,
    openQuestion,
    auditEvent,
    session,
    founder,
    organization,
    apiKey,
  ] = await Promise.all([
    db.upload.count(),
    db.conclusion.count(),
    db.publicationReview.count(),
    db.publishedConclusion.count(),
    db.publicResponse.count(),
    db.contradiction.count(),
    db.driftEvent.count(),
    db.researchSuggestion.count(),
    db.reviewItem.count(),
    db.openQuestion.count(),
    db.auditEvent.count(),
    db.session.count(),
    db.founder.count(),
    db.organization.count(),
    db.apiKey.count(),
  ]);
  return {
    upload,
    conclusion,
    publicationReview,
    publishedConclusion,
    publicResponse,
    contradiction,
    driftEvent,
    researchSuggestion,
    reviewItem,
    openQuestion,
    auditEvent,
    session,
    founder,
    organization,
    apiKey,
  };
}

function fmt(counts: Counts, highlight: Set<string>): string {
  const keys = Object.keys(counts);
  const width = Math.max(...keys.map((k) => k.length));
  return keys
    .map((k) => {
      const mark = highlight.has(k) ? (counts[k]! > 0 ? "✗" : "·") : "○";
      return `  ${mark} ${k.padEnd(width)}  ${counts[k]}`;
    })
    .join("\n");
}

async function main() {
  console.log("\nTheseus Codex — clear library");
  console.log("────────────────────────────");

  const willDelete = new Set<string>([
    "upload",
    "conclusion",
    "publicationReview",
    "publishedConclusion",
    "publicResponse",
    "contradiction",
    "driftEvent",
    "researchSuggestion",
    "reviewItem",
    "openQuestion",
  ]);
  if (!KEEP_AUDIT) willDelete.add("auditEvent");
  if (ALSO_SESSIONS) willDelete.add("session");

  const before = await tally();
  console.log("\nCurrent row counts:");
  console.log(fmt(before, willDelete));
  console.log(
    `\nLegend: ✗ = will delete (rows exist)   · = will delete (empty)   ○ = will preserve`,
  );

  const totalToDelete = [...willDelete].reduce((a, k) => a + (before[k] || 0), 0);
  if (totalToDelete === 0) {
    console.log("\nNothing to delete — library is already empty.");
    await db.$disconnect();
    return;
  }

  if (DRY_RUN) {
    console.log("\n--dry-run: no changes made.");
    await db.$disconnect();
    return;
  }

  const ok = await prompt(
    `\nDelete ${totalToDelete} rows across ${willDelete.size} tables? (y/N) `,
  );
  if (!ok) {
    console.log("Aborted.");
    await db.$disconnect();
    return;
  }

  // Delete in dependency order. PublicResponse -> PublishedConclusion ->
  // PublicationReview -> Conclusion. Upload has no incoming FKs from content
  // tables so it can go whenever. AuditEvent references Upload, so upload
  // before upload or upload after? Actually, AuditEvent has onDelete
  // behaviour = SetNull on uploadId, so upload can go first; then nulled
  // AuditEvent rows can be deleted too (we nuke them anyway).
  console.log("");
  const steps: Array<[string, () => Promise<{ count: number }>]> = [
    ["publicResponse", () => db.publicResponse.deleteMany({})],
    ["publishedConclusion", () => db.publishedConclusion.deleteMany({})],
    ["publicationReview", () => db.publicationReview.deleteMany({})],
    ["reviewItem", () => db.reviewItem.deleteMany({})],
    ["openQuestion", () => db.openQuestion.deleteMany({})],
    ["researchSuggestion", () => db.researchSuggestion.deleteMany({})],
    ["contradiction", () => db.contradiction.deleteMany({})],
    ["driftEvent", () => db.driftEvent.deleteMany({})],
    ["conclusion", () => db.conclusion.deleteMany({})],
    ["upload", () => db.upload.deleteMany({})],
  ];
  if (!KEEP_AUDIT) steps.push(["auditEvent", () => db.auditEvent.deleteMany({})]);
  if (ALSO_SESSIONS) steps.push(["session", () => db.session.deleteMany({})]);

  for (const [name, fn] of steps) {
    const res = await fn();
    console.log(`  ✓ ${name}: deleted ${res.count}`);
  }

  const after = await tally();
  console.log("\nAfter:");
  console.log(fmt(after, willDelete));

  console.log("\nDone. Founders and organizations are preserved — you can still log in.");
  if (!ALSO_SESSIONS && after.session > 0) {
    console.log(
      `(${after.session} active browser session(s) preserved. Use --also-sessions to force re-login.)`,
    );
  }
}

main()
  .catch((e) => {
    console.error("\nClear failed:", e);
    process.exit(1);
  })
  .finally(() => db.$disconnect());
