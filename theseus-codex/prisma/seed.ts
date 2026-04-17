/**
 * Seed script — two founders from env + mock Noosphere-shaped rows for UI.
 *
 * Required env (see .env.example):
 *   SEED_FOUNDER_A_EMAIL, SEED_FOUNDER_A_PASSWORD
 *   SEED_FOUNDER_B_EMAIL, SEED_FOUNDER_B_PASSWORD
 */

import { PrismaClient } from "@prisma/client";
import bcrypt from "bcryptjs";

import { createSqlAdapter } from "../src/lib/prismaAdapter";

if (!process.env.DATABASE_URL) {
  console.error("DATABASE_URL is required for seeding.");
  process.exit(1);
}
const db = new PrismaClient({ adapter: createSqlAdapter() });
const SALT_ROUNDS = 12;

async function main() {
  const aEmail = process.env.SEED_FOUNDER_A_EMAIL;
  const aPass = process.env.SEED_FOUNDER_A_PASSWORD;
  const bEmail = process.env.SEED_FOUNDER_B_EMAIL;
  const bPass = process.env.SEED_FOUNDER_B_PASSWORD;

  if (!aEmail || !aPass || !bEmail || !bPass) {
    console.error(
      "Missing seed env vars. Set SEED_FOUNDER_A_EMAIL, SEED_FOUNDER_A_PASSWORD, " +
        "SEED_FOUNDER_B_EMAIL, SEED_FOUNDER_B_PASSWORD",
    );
    process.exit(1);
  }

  console.log("Seeding Theseus Codex…\n");

  const org = await db.organization.upsert({
    where: { slug: "theseus-local" },
    create: { name: "Theseus (local dev)", slug: "theseus-local" },
    update: { name: "Theseus (local dev)" },
  });
  console.log(`  ✓  Organization ${org.name} (${org.slug})`);

  const founders = [
    {
      name: "Founder Alpha",
      username: "alpha",
      email: aEmail,
      password: aPass,
      role: "admin",
      bio: "Seeded admin (credentials from env).",
      noosphereId: "seed-founder-alpha",
    },
    {
      name: "Founder Beta",
      username: "beta",
      email: bEmail,
      password: bPass,
      role: "founder",
      bio: "Seeded founder (credentials from env).",
      noosphereId: "seed-founder-beta",
    },
  ];

  const created: { id: string; email: string }[] = [];

  for (const f of founders) {
    const passwordHash = await bcrypt.hash(f.password, SALT_ROUNDS);
    const row = await db.founder.upsert({
      where: {
        organizationId_email: { organizationId: org.id, email: f.email },
      },
      create: {
        organizationId: org.id,
        name: f.name,
        username: f.username,
        email: f.email,
        passwordHash,
        role: f.role,
        bio: f.bio,
        noosphereId: f.noosphereId,
      },
      update: {
        name: f.name,
        passwordHash,
        role: f.role,
        bio: f.bio,
        noosphereId: f.noosphereId,
      },
    });
    created.push({ id: row.id, email: row.email });
    console.log(`  ✓  Founder ${f.name} <${f.email}>`);
  }

  const alphaId = created[0]!.id;

  // Mock conclusions (ConfidenceTier + Conclusion fields)
  const conclusionSeeds = [
    {
      text: "Unresolved tensions between fast iteration and epistemic rigor should be surfaced explicitly in every roadmap review.",
      confidenceTier: "open" as const,
      rationale: "Dissent on trade-off framing across two sessions.",
      topicHint: "methodology",
    },
    {
      text: "The firm treats base-rate neglect as a first-class failure mode in investment memos.",
      confidenceTier: "firm" as const,
      rationale: "High cross-founder agreement; repeatedly reinforced.",
      topicHint: "strategy",
    },
    {
      text: "Geometric coherence signals are useful but insufficient without judge-layer override.",
      confidenceTier: "founder" as const,
      rationale: "Two founders endorsed; one abstained pending calibration data.",
      topicHint: "coherence",
    },
  ];

  await db.conclusion.deleteMany({ where: { noosphereId: { startsWith: "seed-conc-" } } });
  for (let i = 0; i < conclusionSeeds.length; i++) {
    const c = conclusionSeeds[i]!;
    await db.conclusion.create({
      data: {
        organizationId: org.id,
        noosphereId: `seed-conc-${i}`,
        text: c.text,
        confidenceTier: c.confidenceTier,
        rationale: c.rationale,
        supportingPrincipleIds: JSON.stringify(["p_seed_1"]),
        evidenceChainClaimIds: JSON.stringify(["claim_seed_a", "claim_seed_b"]),
        dissentClaimIds: JSON.stringify([]),
        confidence: 0.55 + i * 0.1,
        topicHint: c.topicHint,
        attributedFounderId: i === 2 ? alphaId : null,
      },
    });
  }
  console.log(`  ✓  ${conclusionSeeds.length} mock conclusions`);

  await db.driftEvent.deleteMany({ where: { noosphereId: { startsWith: "seed-drift-" } } });
  await db.driftEvent.create({
    data: {
      organizationId: org.id,
      noosphereId: "seed-drift-1",
      targetId: "principle_seed_1",
      targetKind: "principle",
      episodeId: "ep_12",
      observedAt: new Date("2026-03-01"),
      driftScore: 0.42,
      notes: "Embedding centroid shifted after episode 12 claims.",
      naturalLanguageSummary: "Position on falsifiability thresholds softened vs episode 9.",
      claimSequenceIdsJson: JSON.stringify(["c1", "c2", "c3"]),
    },
  });
  console.log("  ✓  Mock drift event");

  await db.contradiction.deleteMany({});
  await db.contradiction.create({
    data: {
      organizationId: org.id,
      claimAId: "claim_alpha",
      claimBId: "claim_beta",
      severity: 0.82,
      sixLayerJson: JSON.stringify({
        s1_consistency: 0.2,
        s2_argumentation: 0.35,
        s3_probabilistic: 0.5,
        s4_geometric: 0.72,
        s5_compression: 0.4,
        s6_llm_judge: 0.68,
      }),
      narrative: "Strong cross-layer disagreement on causal direction.",
    },
  });
  console.log("  ✓  Mock contradiction");

  await db.researchSuggestion.deleteMany({ where: { noosphereId: { startsWith: "seed-rs-" } } });
  await db.researchSuggestion.create({
    data: {
      organizationId: org.id,
      noosphereId: "seed-rs-1",
      title: "Read: Geometry of Unresolution",
      summary: "Formalizes partial orders on unresolved belief states.",
      rationale: "Aligns with open coherence items in recent sessions.",
      readingUris: JSON.stringify(["https://example.org/geometry-unresolution"]),
      sessionLabel: "ep_12",
      suggestedForFounderId: alphaId,
    },
  });
  console.log("  ✓  Mock research suggestion");

  await db.openQuestion.deleteMany({ where: { noosphereId: { startsWith: "seed-oq-" } } });
  await db.openQuestion.create({
    data: {
      organizationId: org.id,
      noosphereId: "seed-oq-1",
      summary: "Do we treat LLM judge scores as epistemic or instrumental evidence?",
      claimAId: "claim_judge",
      claimBId: "claim_human",
      unresolvedReason: "Layer 6 vs layer 4 verdict split > threshold.",
      layerDisagreementSummary: "s4_geometric vs s6_llm_judge",
    },
  });
  console.log("  ✓  Mock open question");

  await db.reviewItem.deleteMany({ where: { noosphereId: { startsWith: "seed-rev-" } } });
  await db.reviewItem.create({
    data: {
      organizationId: org.id,
      noosphereId: "seed-rev-1",
      claimAId: "claim_alpha",
      claimBId: "claim_beta",
      reason: "Aggregator said cohere; layers 1–3 lean contradict.",
      layerVerdictsJson: JSON.stringify({
        s1_consistency: "contradict",
        s2_argumentation: "contradict",
        s3_probabilistic: "unresolved",
        s4_geometric: "cohere",
        s5_compression: "cohere",
        s6_llm_judge: "cohere",
      }),
      severity: 0.91,
      status: "open",
      aggregatorVerdict: "cohere",
      priorScoresJson: JSON.stringify({
        s1_consistency: 0.25,
        s2_argumentation: 0.3,
        s3_probabilistic: 0.55,
        s4_geometric: 0.78,
        s5_compression: 0.7,
        s6_llm_judge: 0.8,
      }),
    },
  });
  console.log("  ✓  Mock review queue item");

  console.log("\nSeed complete.");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => db.$disconnect());
