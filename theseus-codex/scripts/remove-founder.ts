/**
 * Remove a founder account from the live Codex database.
 *
 * Usage:
 *
 *   DATABASE_URL="$DIRECT_URL" \
 *   REMOVE_FOUNDER_EMAIL="someone@example.com" \
 *   REMOVE_FOUNDER_ORG="theseus-local" \   # optional
 *   REMOVE_FOUNDER_FORCE=1 \               # optional: skip the confirm
 *   npx tsx scripts/remove-founder.ts
 *
 * How it handles relations:
 *   - `Session` rows cascade automatically (schema has `onDelete: Cascade`),
 *     but we still explicitly delete them up-front for a clear audit log.
 *   - `ApiKey` rows cascade automatically.
 *   - `Upload`, `AuditEvent` require `founderId` (no cascade, default
 *     `NoAction`). We refuse to delete a founder who owns uploads — those
 *     are real firm artefacts. Audit events are log data and can be safely
 *     deleted alongside the founder.
 *   - Optional relations (`Conclusion.attributedFounderId`,
 *     `PublicationReview.reviewerFounderId`, `ResearchSuggestion.
 *     suggestedForFounderId`, `ReviewItem.resolvedByFounderId`) are
 *     nulled out so those records keep their content but lose the attribution.
 *
 * Prefer `DIRECT_URL` (port 5432) over the pooler — same reason as
 * `add-founder.ts`: Prisma wants a direct connection for multi-row
 * transactions and pgbouncer in transaction mode strips the session state.
 */

import { PrismaClient } from "@prisma/client";

import { createSqlAdapter } from "../src/lib/prismaAdapter";

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v || v.trim() === "") {
    throw new Error(`${name} is required`);
  }
  return v;
}

function envOr(name: string, fallback: string): string {
  const v = process.env[name];
  return v && v.trim() !== "" ? v : fallback;
}

async function main(): Promise<void> {
  if (!process.env.DATABASE_URL) {
    throw new Error(
      "DATABASE_URL must be set (point at your DIRECT_URL for writes)",
    );
  }

  const email = requireEnv("REMOVE_FOUNDER_EMAIL").trim().toLowerCase();
  const orgSlug = envOr(
    "REMOVE_FOUNDER_ORG",
    envOr("DEFAULT_ORGANIZATION_SLUG", "theseus-local"),
  );
  const force = process.env.REMOVE_FOUNDER_FORCE === "1";

  const db = new PrismaClient({ adapter: createSqlAdapter() });

  try {
    const org = await db.organization.findUnique({ where: { slug: orgSlug } });
    if (!org) {
      throw new Error(`Organization '${orgSlug}' not found.`);
    }

    const founder = await db.founder.findUnique({
      where: {
        organizationId_email: { organizationId: org.id, email },
      },
      select: {
        id: true,
        name: true,
        email: true,
        username: true,
        role: true,
      },
    });
    if (!founder) {
      console.log(
        `No founder with email '${email}' in organization '${orgSlug}'. Nothing to do.`,
      );
      return;
    }

    // Count dependents. Uploads are the blocker — real firm artefacts — we
    // refuse to delete a founder who has any. Everything else can be
    // handled (cascaded, nulled, or log-deleted).
    const [uploads, auditEvents, sessions, apiKeys, conclusions, reviews, suggestions, reviewItems] =
      await Promise.all([
        db.upload.count({ where: { founderId: founder.id } }),
        db.auditEvent.count({ where: { founderId: founder.id } }),
        db.session.count({ where: { founderId: founder.id } }),
        db.apiKey.count({ where: { founderId: founder.id } }),
        db.conclusion.count({ where: { attributedFounderId: founder.id } }),
        db.publicationReview.count({
          where: { reviewerFounderId: founder.id },
        }),
        db.researchSuggestion.count({
          where: { suggestedForFounderId: founder.id },
        }),
        db.reviewItem.count({ where: { resolvedByFounderId: founder.id } }),
      ]);

    console.log(`Founder: ${founder.name} <${founder.email}>`);
    console.log(`  id       ${founder.id}`);
    console.log(`  role     ${founder.role}`);
    console.log(`  username ${founder.username}`);
    console.log("");
    console.log("Dependents:");
    console.log(`  uploads:              ${uploads}`);
    console.log(`  auditEvents:          ${auditEvents}`);
    console.log(`  sessions:             ${sessions}`);
    console.log(`  apiKeys:              ${apiKeys}`);
    console.log(`  conclusions attrib:   ${conclusions}`);
    console.log(`  publication reviews:  ${reviews}`);
    console.log(`  research suggestions: ${suggestions}`);
    console.log(`  review items:         ${reviewItems}`);
    console.log("");

    if (uploads > 0) {
      throw new Error(
        `Refusing to delete: founder owns ${uploads} upload(s). Reassign or delete those first.`,
      );
    }

    if (!force) {
      // Interactive confirmation. The calling shell can skip this with
      // REMOVE_FOUNDER_FORCE=1. We use stdin even though the caller might
      // pipe — if stdin isn't a TTY, we refuse to proceed, matching the
      // sync-to-github.sh pattern where non-interactive means "bail".
      if (!process.stdin.isTTY) {
        throw new Error(
          "Non-interactive; set REMOVE_FOUNDER_FORCE=1 to confirm removal.",
        );
      }
      console.log("Type the founder's email to confirm, or anything else to abort:");
      const confirm = await new Promise<string>((resolve) => {
        process.stdin.setEncoding("utf8");
        process.stdin.once("data", (d) => resolve(d.toString().trim()));
      });
      if (confirm !== email) {
        console.log("Confirmation mismatch. Aborting.");
        return;
      }
    }

    // Perform the deletion as a single transaction so a partial failure
    // doesn't leave dangling rows.
    await db.$transaction(async (tx) => {
      // Null out optional attributions (keeps the rows, loses the link).
      await tx.conclusion.updateMany({
        where: { attributedFounderId: founder.id },
        data: { attributedFounderId: null },
      });
      await tx.publicationReview.updateMany({
        where: { reviewerFounderId: founder.id },
        data: { reviewerFounderId: null },
      });
      await tx.researchSuggestion.updateMany({
        where: { suggestedForFounderId: founder.id },
        data: { suggestedForFounderId: null },
      });
      await tx.reviewItem.updateMany({
        where: { resolvedByFounderId: founder.id },
        data: { resolvedByFounderId: null },
      });
      // Explicit deletes for sessions + apiKeys (would cascade anyway, but
      // being explicit makes the audit log clearer).
      await tx.session.deleteMany({ where: { founderId: founder.id } });
      await tx.apiKey.deleteMany({ where: { founderId: founder.id } });
      // Audit events: no cascade, no attribution-null semantics; they're
      // log rows and the subject is gone, so delete them.
      await tx.auditEvent.deleteMany({ where: { founderId: founder.id } });
      // Finally, the founder.
      await tx.founder.delete({ where: { id: founder.id } });
    });

    console.log("");
    console.log(`Removed founder '${email}' from organization '${orgSlug}'.`);
  } finally {
    await db.$disconnect();
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exitCode = 1;
});
