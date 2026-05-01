import { expect, test } from "@playwright/test";
import { PrismaClient } from "@prisma/client";
import { createHash } from "crypto";
import { createSqlAdapter } from "../src/lib/prismaAdapter";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";
const modelName = "e2e-semantic-explorer";

function vectorBytes(values: number[]): Buffer {
  const buf = Buffer.alloc(values.length * 4);
  values.forEach((value, index) => buf.writeFloatLE(value, index * 4));
  return buf;
}

async function ensureEmbeddingTables(db: PrismaClient) {
  await db.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS embedding_model_version (
      id TEXT PRIMARY KEY,
      effective_from TIMESTAMPTZ NOT NULL,
      model_name TEXT NOT NULL,
      notes TEXT NOT NULL DEFAULT ''
    )
  `);
  await db.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS embedding (
      id TEXT PRIMARY KEY,
      model_name TEXT NOT NULL,
      text_sha256 TEXT NOT NULL,
      dimension INTEGER NOT NULL,
      vector BYTEA NOT NULL,
      ref_claim_id TEXT NOT NULL DEFAULT ''
    )
  `);
  await db.$executeRawUnsafe(
    `INSERT INTO embedding_model_version (id, effective_from, model_name, notes)
     VALUES ($1, NOW() - INTERVAL '1 minute', $2, $3)
     ON CONFLICT (id) DO UPDATE
       SET effective_from = EXCLUDED.effective_from,
           model_name = EXCLUDED.model_name,
           notes = EXCLUDED.notes`,
    "e2e-semantic-explorer-model",
    modelName,
    "E2E semantic explorer fixture",
  );
}

async function insertEmbedding(db: PrismaClient, conclusionId: string, values: number[]) {
  await db.$executeRawUnsafe(
    `INSERT INTO embedding (id, model_name, text_sha256, dimension, vector, ref_claim_id)
     VALUES ($1, $2, $3, $4, $5, $6)
     ON CONFLICT (id) DO UPDATE
       SET model_name = EXCLUDED.model_name,
           text_sha256 = EXCLUDED.text_sha256,
           dimension = EXCLUDED.dimension,
           vector = EXCLUDED.vector,
           ref_claim_id = EXCLUDED.ref_claim_id`,
    `e2e_semantic_${conclusionId}`,
    modelName,
    createHash("sha256").update(conclusionId).digest("hex"),
    values.length,
    vectorBytes(values),
    conclusionId,
  );
}

test("semantic explorer warms until three embedded conclusions exist", async ({ page }) => {
  test.skip(
    !process.env.DATABASE_URL || !founderEmail || !founderPassword,
    "DATABASE_URL and seeded founder credentials are required",
  );

  const db = new PrismaClient({ adapter: createSqlAdapter() });
  const noosphereId = `e2e-semantic-explorer-${Date.now()}`;
  const conclusionIds: string[] = [];

  try {
    await ensureEmbeddingTables(db);
    const org = await db.organization.findUnique({
      where: { slug: founderOrg },
      include: { founders: { where: { email: founderEmail! }, take: 1 } },
    });
    expect(org).toBeTruthy();
    const founder = org!.founders[0];
    expect(founder).toBeTruthy();

    for (let index = 0; index < 3; index++) {
      const conclusion = await db.conclusion.create({
        data: {
          organizationId: org!.id,
          noosphereId: `${noosphereId}-${index}`,
          text: `Semantic explorer e2e conclusion ${index}`,
          confidenceTier: index === 0 ? "firm" : "open",
          rationale: "E2E semantic explorer fixture.",
          supportingPrincipleIds: "[]",
          evidenceChainClaimIds: "[]",
          dissentClaimIds: "[]",
          confidence: 0.5,
          topicHint: `e2e-${index}`,
          attributedFounderId: founder!.id,
        },
      });
      conclusionIds.push(conclusion.id);
    }

    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel(/organization/i).fill(founderOrg);
    await page.getByLabel(/email/i).fill(founderEmail!);
    await page.getByLabel(/passphrase/i).fill(founderPassword!);
    await page.getByRole("button", { name: /enter the codex/i }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

    await page.goto("/explorer");
    await expect(page.getByText(/Currently:\s*0\/3/)).toBeVisible();

    await insertEmbedding(db, conclusionIds[0]!, [1, 0, 0]);
    await insertEmbedding(db, conclusionIds[1]!, [0, 1, 0]);
    await page.reload();
    await expect(page.getByText(/Currently:\s*2\/3/)).toBeVisible();

    await insertEmbedding(db, conclusionIds[2]!, [0, 0, 1]);
    await page.reload();
    await expect(page.getByText(/The semantic explorer activates/)).not.toBeVisible();
    await expect(page.getByText("firm")).toBeVisible();
  } finally {
    for (const conclusionId of conclusionIds) {
      await db.$executeRawUnsafe(
        `DELETE FROM embedding WHERE ref_claim_id = $1`,
        conclusionId,
      );
    }
    await db.conclusion.deleteMany({ where: { noosphereId: { startsWith: noosphereId } } });
    await db.$disconnect();
  }
});
