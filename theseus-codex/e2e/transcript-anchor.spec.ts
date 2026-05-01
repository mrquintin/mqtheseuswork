import { expect, test } from "@playwright/test";
import { PrismaClient } from "@prisma/client";
import { createSqlAdapter } from "../src/lib/prismaAdapter";

const founderEmail = process.env.E2E_FOUNDER_EMAIL ?? process.env.SEED_FOUNDER_A_EMAIL;
const founderPassword =
  process.env.E2E_FOUNDER_PASSWORD ?? process.env.SEED_FOUNDER_A_PASSWORD;
const founderOrg = process.env.E2E_FOUNDER_ORG ?? "theseus-local";

test("transcript anchor query scrolls to and highlights the target chunk", async ({ page }) => {
  test.skip(
    !process.env.DATABASE_URL || !founderEmail || !founderPassword,
    "DATABASE_URL and seeded founder credentials are required",
  );

  const db = new PrismaClient({ adapter: createSqlAdapter() });
  const sourceId = `e2e-transcript-anchor-${Date.now()}`;
  let uploadId = "";

  try {
    const org = await db.organization.findUnique({
      where: { slug: founderOrg },
      include: { founders: { where: { email: founderEmail! }, take: 1 } },
    });
    expect(org).toBeTruthy();
    const founder = org!.founders[0];
    expect(founder).toBeTruthy();

    const upload = await db.upload.create({
      data: {
        organizationId: org!.id,
        founderId: founder!.id,
        title: `E2E Transcript Anchor ${sourceId}`,
        description: "E2E transcript anchor fixture.",
        sourceType: "transcript",
        originalName: `${sourceId}.txt`,
        mimeType: "text/plain",
        filePath: `/tmp/${sourceId}.txt`,
        fileSize: 512,
        textContent:
          "[00:00:12] Michael: The first line establishes the archive.\n" +
          "[00:01:30] Ada: The second line is the anchor target.\n" +
          "The final paragraph closes the fixture.",
        blurb:
          "A short fixture transcript used to verify that transcript anchors scroll to the correct line.",
        status: "ingested",
        visibility: "org",
        chunks: {
          create: [
            {
              index: 0,
              text: "The first line establishes the archive.",
              startMs: 12_000,
              speakerLabel: "Michael",
              headingHint: "Archive",
            },
            {
              index: 1,
              text: "The second line is the anchor target.",
              startMs: 90_000,
              speakerLabel: "Ada",
              headingHint: "Anchor Target",
            },
            {
              index: 2,
              text: "The final paragraph closes the fixture.",
            },
          ],
        },
      },
      include: { chunks: { orderBy: { index: "asc" } } },
    });
    uploadId = upload.id;
    const target = upload.chunks[1]!;

    await page.context().clearCookies();
    await page.goto("/login");
    await page.getByLabel(/organization/i).fill(founderOrg);
    await page.getByLabel(/email/i).fill(founderEmail!);
    await page.getByLabel(/passphrase/i).fill(founderPassword!);
    await page.getByRole("button", { name: /enter the codex/i }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 15_000 });

    await page.goto(`/transcripts/${upload.id}?anchor=chunk-${target.id}`);
    const chunk = page.locator(`#chunk-${target.id}`);
    await expect(chunk).toBeVisible();
    await expect(chunk).toHaveClass(/chunk-highlight/);
    await expect
      .poll(async () =>
        chunk.evaluate((el) => {
          const rect = el.getBoundingClientRect();
          return rect.top >= 0 && rect.bottom <= window.innerHeight;
        }),
      )
      .toBe(true);
  } finally {
    if (uploadId) await db.upload.deleteMany({ where: { id: uploadId } });
    await db.$disconnect();
  }
});
