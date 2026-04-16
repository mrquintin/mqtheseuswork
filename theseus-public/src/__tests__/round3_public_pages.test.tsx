import { describe, it, expect, vi } from "vitest";

const { mockRound3, mockPublished } = vi.hoisted(() => ({
  mockRound3: {
    schema: "theseus.round3Export.v1" as const,
    generatedAt: "2026-04-15T00:00:00Z",
    methods: [
      {
        name: "six-layer-coherence",
        version: "1.0.0",
        doi: "10.5281/zenodo.0000001",
        description: "Six-layer coherence verification.",
        bibtex: "@article{slc, title={SLC}}",
        downloadUrl: "/artifacts/methods/slc-1.0.0.tar.gz",
        publishedAt: "2026-03-01T12:00:00Z",
        corpusHash: "sha256:abc123",
        signature: "sig:abc123",
        parameters: { layers: 6 },
        versionHistory: [
          { version: "1.0.0", publishedAt: "2026-03-01T12:00:00Z", changeNote: "Initial" },
        ],
      },
      {
        name: "five-criterion-meta",
        version: "2.0.0",
        doi: "10.5281/zenodo.0000002",
        description: "Five-criterion meta-analysis.",
        bibtex: "@article{fcm, title={FCM}}",
        downloadUrl: "/artifacts/methods/fcm-2.0.0.tar.gz",
        publishedAt: "2026-03-15T12:00:00Z",
        corpusHash: "sha256:def456",
        signature: "sig:def456",
        parameters: {},
        versionHistory: [
          { version: "1.0.0", publishedAt: "2026-02-01T12:00:00Z", changeNote: "Initial" },
          { version: "2.0.0", publishedAt: "2026-03-15T12:00:00Z", changeNote: "Revised" },
        ],
      },
    ],
    mips: [
      {
        name: "mip-001-claim-format",
        version: "1.0.0",
        description: "Claim interchange format.",
        adoptionInstructions: "Validate against the schema.",
        versionMatrix: [
          { version: "1.0.0", publishedAt: "2026-03-15T12:00:00Z", status: "active" },
        ],
        publishedAt: "2026-03-15T12:00:00Z",
        corpusHash: "sha256:mip001",
        signature: "sig:mip001",
      },
    ],
    rigorDashboard: [
      {
        month: "2026-03",
        passCount: 42,
        failCount: 7,
        topFailureCategories: [
          { category: "evidence-gap", count: 3 },
          { category: "coherence-mismatch", count: 2 },
        ],
      },
      {
        month: "2026-02",
        passCount: 38,
        failCount: 5,
        topFailureCategories: [{ category: "calibration-drift", count: 3 }],
      },
    ],
    founderOverrides: [
      {
        id: "ov-001",
        conclusionId: "pub-001",
        field: "discountedConfidence",
        originalValue: "0.82",
        overriddenValue: "0.75",
        justification: "Manual calibration correction.",
        issuedAt: "2026-03-20T10:00:00Z",
        issuedBy: "founder",
      },
    ],
    decayStats: [
      {
        conclusionId: "pub-001",
        slug: "test-conclusion",
        currentConfidence: 0.71,
        originalConfidence: 0.82,
        decayRate: 0.015,
        lastDecayEvent: "2026-04-01T00:00:00Z",
        totalDecayEvents: 3,
      },
    ],
    provenance: {
      "pub-001": {
        conclusionId: "pub-001",
        ledgerEntries: [
          { hash: "sha256:l001", timestamp: "2026-02-28T08:00:00Z", action: "claim-ingested" },
          { hash: "sha256:l002", timestamp: "2026-03-01T12:00:00Z", action: "published" },
        ],
        corpusHashAtPublication: "sha256:corpus001",
      },
    },
    adversarialHistory: {
      "pub-001": [
        {
          round: 1,
          reviewerRole: "devil-advocate",
          outcome: "pass" as const,
          summary: "No material objections.",
        },
      ],
    },
  },
  mockPublished: {
    schema: "theseus.publishedExport.v1" as const,
    generatedAt: "2026-04-15T00:00:00Z",
    conclusions: [
      {
        id: "pub-001",
        slug: "test-conclusion",
        version: 1,
        sourceConclusionId: "src-001",
        publishedAt: "2026-03-01T12:00:00Z",
        doi: "10.5281/zenodo.9999999",
        zenodoRecordId: "9999999",
        discountedConfidence: 0.75,
        statedConfidence: 0.82,
        calibrationDiscountReason: "Novel domain.",
        payload: {
          conclusionText: "Test conclusion for verification.",
          evidenceSummary: "Evidence summary.",
          exitConditions: ["Condition A"],
          strongestObjection: { objection: "Objection", firmAnswer: "Answer" },
          openQuestionsAdjacent: [],
          voiceComparisons: [],
          timeline: [],
          whatWouldChangeOurMind: [],
          citations: [],
        },
      },
    ],
    openQuestions: [],
    responses: [],
  },
}));

vi.mock("../../content/round3.json", () => ({ default: mockRound3 }));
vi.mock("../../content/published.json", () => ({ default: mockPublished }));
vi.mock("next/navigation", () => ({ notFound: vi.fn() }));
vi.mock("next/link", () => ({ default: vi.fn(({ children }: { children: React.ReactNode }) => children) }));
vi.mock("@/components/CopyButton", () => ({ default: vi.fn(() => null) }));

import {
  allMethods,
  pickMethod,
  allMips,
  pickMip,
  rigorDashboard,
  allOverrides,
  allDecayStats,
  provenanceFor,
  adversarialHistoryFor,
  conclusionById,
} from "@/lib/api/round3";

describe("round3 data fetchers", () => {
  describe("allMethods", () => {
    it("returns methods sorted by name", () => {
      const methods = allMethods();
      expect(methods).toHaveLength(2);
      expect(methods[0].name).toBe("five-criterion-meta");
      expect(methods[1].name).toBe("six-layer-coherence");
    });

    it("returns a new array each call (no mutation risk)", () => {
      const a = allMethods();
      const b = allMethods();
      expect(a).not.toBe(b);
    });
  });

  describe("pickMethod", () => {
    it("returns method by name and version", () => {
      const m = pickMethod("six-layer-coherence", "1.0.0");
      expect(m).not.toBeNull();
      expect(m!.name).toBe("six-layer-coherence");
      expect(m!.version).toBe("1.0.0");
    });

    it("returns latest if no version specified", () => {
      const m = pickMethod("five-criterion-meta");
      expect(m).not.toBeNull();
      expect(m!.version).toBe("2.0.0");
    });

    it("returns null for unknown method", () => {
      expect(pickMethod("nonexistent")).toBeNull();
    });

    it("returns null for unknown version of known method", () => {
      expect(pickMethod("six-layer-coherence", "9.9.9")).toBeNull();
    });
  });

  describe("allMips", () => {
    it("returns MIPs sorted by name", () => {
      const mips = allMips();
      expect(mips).toHaveLength(1);
      expect(mips[0].name).toBe("mip-001-claim-format");
    });
  });

  describe("pickMip", () => {
    it("returns MIP by name and version", () => {
      const m = pickMip("mip-001-claim-format", "1.0.0");
      expect(m).not.toBeNull();
      expect(m!.version).toBe("1.0.0");
    });

    it("returns null for unknown MIP", () => {
      expect(pickMip("nonexistent")).toBeNull();
    });
  });

  describe("rigorDashboard", () => {
    it("returns months in reverse chronological order", () => {
      const months = rigorDashboard();
      expect(months).toHaveLength(2);
      expect(months[0].month).toBe("2026-03");
      expect(months[1].month).toBe("2026-02");
    });

    it("includes failure categories", () => {
      const months = rigorDashboard();
      expect(months[0].topFailureCategories.length).toBeGreaterThan(0);
    });
  });

  describe("allOverrides", () => {
    it("returns overrides with justification", () => {
      const overrides = allOverrides();
      expect(overrides).toHaveLength(1);
      expect(overrides[0].justification).toBeTruthy();
      expect(overrides[0].field).toBe("discountedConfidence");
    });
  });

  describe("allDecayStats", () => {
    it("returns decay stats sorted by slug", () => {
      const stats = allDecayStats();
      expect(stats).toHaveLength(1);
      expect(stats[0].slug).toBe("test-conclusion");
      expect(stats[0].currentConfidence).toBeLessThan(stats[0].originalConfidence);
    });
  });

  describe("provenanceFor", () => {
    it("returns provenance for known conclusion", () => {
      const p = provenanceFor("pub-001");
      expect(p).not.toBeNull();
      expect(p!.ledgerEntries.length).toBeGreaterThan(0);
      expect(p!.corpusHashAtPublication).toBeTruthy();
    });

    it("returns null for unknown conclusion", () => {
      expect(provenanceFor("nonexistent")).toBeNull();
    });
  });

  describe("adversarialHistoryFor", () => {
    it("returns adversarial history for known conclusion", () => {
      const history = adversarialHistoryFor("pub-001");
      expect(history).toHaveLength(1);
      expect(history[0].reviewerRole).toBe("devil-advocate");
    });

    it("returns empty array for unknown conclusion", () => {
      expect(adversarialHistoryFor("nonexistent")).toEqual([]);
    });

    it("exposes only roles — never agent identities or private rationales", () => {
      const history = adversarialHistoryFor("pub-001");
      for (const entry of history) {
        expect(entry).not.toHaveProperty("agentId");
        expect(entry).not.toHaveProperty("agentIdentity");
        expect(entry).not.toHaveProperty("privateRationale");
        expect(entry).toHaveProperty("reviewerRole");
        expect(entry).toHaveProperty("summary");
      }
    });
  });

  describe("conclusionById", () => {
    it("returns conclusion by ID", () => {
      const c = conclusionById("pub-001");
      expect(c).not.toBeNull();
      expect(c!.slug).toBe("test-conclusion");
    });

    it("returns null for unknown ID", () => {
      expect(conclusionById("nonexistent")).toBeNull();
    });
  });
});

describe("read-only policy", () => {
  it("round3 module exports no write/mutate functions", async () => {
    const mod = await import("@/lib/api/round3");
    const exportNames = Object.keys(mod);
    const writeLike = exportNames.filter((n) =>
      /^(create|update|delete|remove|write|mutate|insert|post|put|patch)/i.test(n),
    );
    expect(writeLike).toEqual([]);
  });
});

describe("page module exports", () => {
  it("methods page exports default component", async () => {
    const mod = await import("@/app/methods/page");
    expect(mod.default).toBeDefined();
    expect(typeof mod.default).toBe("function");
  });

  it("methods detail page exports generateStaticParams and generateMetadata", async () => {
    const mod = await import("@/app/methods/[name]/[version]/page");
    expect(mod.generateStaticParams).toBeDefined();
    expect(mod.generateMetadata).toBeDefined();
  });

  it("interop page exports default component", async () => {
    const mod = await import("@/app/interop/page");
    expect(mod.default).toBeDefined();
    expect(typeof mod.default).toBe("function");
  });

  it("interop detail page exports generateStaticParams and generateMetadata", async () => {
    const mod = await import("@/app/interop/[mipName]/[mipVersion]/page");
    expect(mod.generateStaticParams).toBeDefined();
    expect(mod.generateMetadata).toBeDefined();
  });

  it("rigor page exports default component", async () => {
    const mod = await import("@/app/methodology/rigor/page");
    expect(mod.default).toBeDefined();
    expect(typeof mod.default).toBe("function");
  });

  it("overrides page exports default component", async () => {
    const mod = await import("@/app/methodology/overrides/page");
    expect(mod.default).toBeDefined();
    expect(typeof mod.default).toBe("function");
  });

  it("decay page exports default component", async () => {
    const mod = await import("@/app/methodology/decay/page");
    expect(mod.default).toBeDefined();
    expect(typeof mod.default).toBe("function");
  });

  it("conclusion-by-id page exports generateStaticParams and generateMetadata", async () => {
    const mod = await import("@/app/conclusions/[id]/page");
    expect(mod.generateStaticParams).toBeDefined();
    expect(mod.generateMetadata).toBeDefined();
  });
});

describe("generateStaticParams", () => {
  it("methods detail produces params for all methods", async () => {
    const mod = await import("@/app/methods/[name]/[version]/page");
    const params = await mod.generateStaticParams();
    expect(params).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: "six-layer-coherence", version: "1.0.0" }),
      ]),
    );
  });

  it("interop detail produces params for all MIPs", async () => {
    const mod = await import("@/app/interop/[mipName]/[mipVersion]/page");
    const params = await mod.generateStaticParams();
    expect(params).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ mipName: "mip-001-claim-format", mipVersion: "1.0.0" }),
      ]),
    );
  });

  it("conclusions-by-id produces params for all published conclusions", async () => {
    const mod = await import("@/app/conclusions/[id]/page");
    const params = await mod.generateStaticParams();
    expect(params).toEqual(expect.arrayContaining([{ id: "pub-001" }]));
  });
});
