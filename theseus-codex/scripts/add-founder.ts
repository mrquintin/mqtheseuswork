/**
 * Add (or update) a founder account in the live Codex database.
 *
 * Usage (values come from env vars so passwords never appear on argv,
 * which would get echoed to shell history / process listings):
 *
 *   DATABASE_URL="$DIRECT_URL" \
 *   ADD_FOUNDER_EMAIL="someone@example.com" \
 *   ADD_FOUNDER_PASSWORD="..." \
 *   ADD_FOUNDER_USERNAME="someone" \       # optional; defaults to email prefix
 *   ADD_FOUNDER_NAME="Some One" \          # optional; defaults to username
 *   ADD_FOUNDER_ROLE="founder" \           # optional; 'founder' | 'admin'
 *   ADD_FOUNDER_ORG="theseus-local" \      # optional; defaults to DEFAULT_ORGANIZATION_SLUG
 *   npx tsx scripts/add-founder.ts
 *
 * Upserts by (organizationId, email), so re-running with the same email
 * safely resets the password without creating a duplicate row. This is the
 * ONLY way to reset a password today — the Codex has no password-reset UI
 * yet.
 *
 * Prefer `DIRECT_URL` (port 5432) over the pooler URL: Prisma wants a direct
 * connection for write-heavy operations and the migration lock it acquires
 * gets stripped by pgbouncer in transaction mode.
 */

import { PrismaClient } from "@prisma/client";
import bcrypt from "bcryptjs";

import { createSqlAdapter } from "../src/lib/prismaAdapter";

const SALT_ROUNDS = 12;

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v || v.trim() === "") {
    throw new Error(`${name} is required (set it in the env before running)`);
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
      "DATABASE_URL must be set (point it at your DIRECT_URL for writes)",
    );
  }

  const email = requireEnv("ADD_FOUNDER_EMAIL").trim().toLowerCase();
  const password = requireEnv("ADD_FOUNDER_PASSWORD");
  const orgSlug = envOr(
    "ADD_FOUNDER_ORG",
    envOr("DEFAULT_ORGANIZATION_SLUG", "theseus-local"),
  );

  const emailLocal = email.split("@")[0]!;
  const username = envOr("ADD_FOUNDER_USERNAME", emailLocal).trim();
  const name = envOr("ADD_FOUNDER_NAME", username);
  const role = envOr("ADD_FOUNDER_ROLE", "founder");

  if (password.length < 8) {
    throw new Error("Password must be at least 8 characters");
  }
  if (!email.includes("@")) {
    throw new Error(`Email doesn't look valid: ${email}`);
  }
  if (role !== "founder" && role !== "admin") {
    throw new Error(`Role must be 'founder' or 'admin' (got '${role}')`);
  }

  const db = new PrismaClient({ adapter: createSqlAdapter() });

  try {
    const org = await db.organization.findUnique({ where: { slug: orgSlug } });
    if (!org) {
      throw new Error(
        `Organization '${orgSlug}' not found. Seed it first or pass ADD_FOUNDER_ORG.`,
      );
    }

    const passwordHash = await bcrypt.hash(password, SALT_ROUNDS);

    const existing = await db.founder.findUnique({
      where: {
        organizationId_email: { organizationId: org.id, email },
      },
      select: { id: true, name: true },
    });

    const row = await db.founder.upsert({
      where: {
        organizationId_email: { organizationId: org.id, email },
      },
      create: {
        organizationId: org.id,
        name,
        username,
        email,
        passwordHash,
        role,
        bio: "",
      },
      update: {
        // On re-runs, update the password + profile but leave the bio alone
        // (which may have been edited in the UI after initial creation).
        passwordHash,
        name,
        username,
        role,
      },
      select: { id: true, email: true, username: true, role: true, name: true },
    });

    const verb = existing ? "Updated" : "Created";
    console.log(`${verb} founder in organization '${orgSlug}':`);
    console.log(`  id        ${row.id}`);
    console.log(`  name      ${row.name}`);
    console.log(`  email     ${row.email}`);
    console.log(`  username  ${row.username}`);
    console.log(`  role      ${row.role}`);
    console.log("");
    console.log("Log in at /login with:");
    console.log(`  organization slug: ${orgSlug}`);
    console.log(`  email:             ${email}`);
    console.log(`  password:          <the ADD_FOUNDER_PASSWORD you supplied>`);
  } finally {
    await db.$disconnect();
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exitCode = 1;
});
