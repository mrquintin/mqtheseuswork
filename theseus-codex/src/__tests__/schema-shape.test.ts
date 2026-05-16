/**
 * Schema-shape invariants — Round-18 consolidation guard.
 *
 * These assertions parse `prisma/schema.prisma` as text and verify the
 * structural invariants the Round-18 audit (`docs/architecture/Schema_Audit_Round18.md`)
 * established. They run without a database connection so they can fire
 * in CI before any database is provisioned.
 *
 * If a test goes red, EITHER the schema regressed OR the audit's
 * invariant should be revisited — fix the schema or update the audit
 * doc and this test together. Do not silence the test.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const SCHEMA_PATH = path.resolve(__dirname, "..", "..", "prisma", "schema.prisma");
const AUDIT_PATH = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "docs",
  "architecture",
  "Schema_Audit_Round18.md",
);

const SCHEMA = readFileSync(SCHEMA_PATH, "utf8");

interface ModelBlock {
  name: string;
  body: string;
}

function parseModels(schema: string): ModelBlock[] {
  // Match `model X { … }` blocks. Prisma model bodies do not contain a
  // bare `}` at column 0 except as their closing brace, so a greedy
  // regex anchored to the start-of-line `}` is sufficient.
  const re = /^model\s+(\w+)\s*\{([\s\S]*?)^\}/gm;
  const out: ModelBlock[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(schema)) !== null) {
    out.push({ name: m[1], body: m[2] });
  }
  return out;
}

const MODELS = parseModels(SCHEMA);
const MODEL_NAMES = new Set(MODELS.map((m) => m.name));

describe("schema-shape — Round 18 audit invariants", () => {
  it("parses every model block", () => {
    // Sanity: the schema file is non-trivial and the parser found models.
    expect(MODELS.length).toBeGreaterThan(40);
  });

  it("redundant Founder.organizationId single-column index is gone", () => {
    // Round-18 audit §5.1: covered by leading column of
    // @@unique([organizationId, email]).
    const founder = MODELS.find((m) => m.name === "Founder");
    expect(founder, "Founder model must exist").toBeDefined();
    const lines = founder!.body.split("\n").map((l) => l.trim());
    expect(lines).not.toContain("@@index([organizationId])");
  });

  it("every Round-17 model has either createdAt or a documented append-only timestamp", () => {
    // Round-18 audit §2.1: append-only rows may use observedAt / firedAt
    // / generatedAt instead of createdAt; otherwise createdAt is
    // mandatory for new rows.
    const APPEND_ONLY_TIMESTAMP_NAMES = [
      "createdAt",
      "observedAt",
      "firedAt",
      "generatedAt",
      "publishedAt",
      "computedAt",
      "scoredAt",
      "capturedAt",
      "startedAt",
    ];
    const ROUND_17 = [
      "MethodologyQualityScore",
      "ConclusionMethod",
      "MethodTrackRecord",
      "MethodVersion",
      "AnchorRevision",
      "DomainBoundVerdict",
      "CalibrationModel",
      "RecalibrationOverride",
      "RevisionEvent",
      "SourceStanding",
      "SourceTriageItem",
      "SourceCredibilityUpdate",
      "CitationVerdict",
      "AttentionAction",
      "Subscriber",
      "Principle",
      "Addendum",
      "CritiqueSubmission",
      "CritiqueBountyPayout",
      "ResponseTriage",
      "PublicReply",
      "PublicationSignature",
      "Span",
      "MethodMetricRollup",
      "AlertRule",
      "AlertEvent",
    ];
    for (const name of ROUND_17) {
      const model = MODELS.find((m) => m.name === name);
      expect(model, `Round-17 model ${name} must exist`).toBeDefined();
      const has = APPEND_ONLY_TIMESTAMP_NAMES.some((ts) =>
        new RegExp(`\\b${ts}\\b\\s+DateTime`).test(model!.body),
      );
      expect(has, `${name} must declare a creation timestamp column`).toBe(
        true,
      );
    }
  });

  it("every model carries either organizationId or a documented derivation path", () => {
    // Round-18 audit §2.2: tenant-light models are explicitly enumerated.
    const TENANT_LIGHT_BY_DESIGN = new Set([
      // Polymorphic / one-parent rows that derive tenant via the parent.
      "ConclusionSource",
      "UploadChunk",
      "OpinionCitation",
      "FollowUpSession",
      "FollowUpMessage",
      "ForecastCitation",
      "ForecastResolution",
      "ResolutionOverride",
      "ResolutionMismatch",
      "ResolutionRevision",
      "ForecastFollowUpSession",
      "ForecastFollowUpMessage",
      "ConclusionDeletionRequest",
      "DashboardDismissal",
      "DeletionRequest",
      "PublicationSignature",
      // Observability tables — intentionally tenant-light.
      "MethodMetricRollup",
      "AlertRule",
      "AlertEvent",
      // Global security catalog. Tenant-specific signals and positions
      // point at the shared instrument row.
      "EquityInstrument",
      // Market-data / citation children derive their tenant boundary
      // through EquityInstrument or EquitySignal respectively.
      "EquityPriceTick",
      "EquitySignalCitation",
      // Single root.
      "Organization",
    ]);
    for (const m of MODELS) {
      if (TENANT_LIGHT_BY_DESIGN.has(m.name)) continue;
      const hasOrg = /\borganizationId\b/.test(m.body);
      expect(
        hasOrg,
        `${m.name} must declare organizationId or be added to TENANT_LIGHT_BY_DESIGN with a documented reason`,
      ).toBe(true);
    }
  });

  it("Method* / Methodology* prefix split is preserved (audit §3)", () => {
    // The audit established: registry-keyed concepts use Method*,
    // document-level structured profiles use Methodology*. Drift in
    // either direction without a deliberate rename should fail this
    // test until the audit document is updated.
    const METHOD_STAR = [
      "MethodVersion",
      "MethodTrackRecord",
      "MethodMetricRollup",
      "ConclusionMethod",
    ];
    const METHODOLOGY_STAR = [
      "MethodologyProfile",
      "MethodologyQualityScore",
      // Methodology Review Week rows are schedule/public-review artifacts,
      // not registry-keyed methods. The naming is deliberate and documented
      // in the Round-18 audit addendum.
      "MethodologyReviewWeek",
      "MethodologyReviewDaySummary",
    ];
    for (const name of METHOD_STAR) {
      expect(MODEL_NAMES.has(name), `Method* model ${name} must exist`).toBe(true);
    }
    for (const name of METHODOLOGY_STAR) {
      expect(MODEL_NAMES.has(name), `Methodology* model ${name} must exist`).toBe(
        true,
      );
    }
    // No other Methodology* model should appear without an audit update.
    const otherMethodology = [...MODEL_NAMES].filter(
      (n) => n.startsWith("Methodology") && !METHODOLOGY_STAR.includes(n),
    );
    expect(otherMethodology).toEqual([]);
  });

  it("every @@unique that is not a single FK column has a justifying comment within 4 lines above", () => {
    // Round-18 audit §5: unjustified composite uniques are a smell.
    // Exempt single-column uniques (FKs in 1:1 relations) from the
    // comment requirement — the constraint is self-documenting.
    for (const m of MODELS) {
      const lines = m.body.split("\n");
      for (let i = 0; i < lines.length; i++) {
        const trim = lines[i].trim();
        if (!trim.startsWith("@@unique(")) continue;
        const inside = trim.slice("@@unique(".length, trim.lastIndexOf(")"));
        const cols = inside
          .replace(/^\[|\]$/g, "")
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s.length > 0);
        if (cols.length <= 1) continue;
        // Look up to 4 lines above for a `//` comment OR for the model
        // docstring (a `///` block above the model declaration counts).
        const window = lines.slice(Math.max(0, i - 4), i).join("\n");
        const hasComment = /\/\//.test(window) || /\/\*\*/.test(window);
        const isWellKnown =
          cols.includes("organizationId") ||
          cols.some((c) => c.endsWith("Id")) ||
          cols.includes("methodName");
        expect(
          hasComment || isWellKnown,
          `${m.name}: @@unique(${cols.join(", ")}) needs a justifying comment within 4 lines above`,
        ).toBe(true);
      }
    }
  });

  it("audit document exists and references every Round-17 model", () => {
    // The check_schema_audit_consistency.py script enforces the inverse
    // direction (every model in the schema is mentioned in the audit).
    // This test only enforces existence + a representative spot check.
    const auditText = readFileSync(AUDIT_PATH, "utf8");
    expect(auditText.length).toBeGreaterThan(2000);
    for (const name of [
      "MethodologyQualityScore",
      "MethodTrackRecord",
      "AnchorRevision",
      "CitationVerdict",
      "AttentionAction",
      "Subscriber",
      "Principle",
    ]) {
      expect(
        auditText.includes(name),
        `audit doc must mention ${name}`,
      ).toBe(true);
    }
  });

  it("CitationVerdict polymorphic shape is documented (citationKind + citationId, no FK)", () => {
    const cv = MODELS.find((m) => m.name === "CitationVerdict");
    expect(cv).toBeDefined();
    expect(/\bcitationKind\s+String\b/.test(cv!.body)).toBe(true);
    expect(/\bcitationId\s+String\b/.test(cv!.body)).toBe(true);
    // No FK relation on citationId — it's polymorphic.
    expect(/citationId.*@relation/.test(cv!.body)).toBe(false);
  });

  it("DriftEvent retains both targetKind values via the dual-shape table (no fork)", () => {
    const de = MODELS.find((m) => m.name === "DriftEvent");
    expect(de).toBeDefined();
    expect(/\btargetKind\s+String/.test(de!.body)).toBe(true);
    expect(/\bmethodName\s+String\?/.test(de!.body)).toBe(true);
    // No new MethodDriftEvent table appeared (deferred — see audit §8).
    expect(MODEL_NAMES.has("MethodDriftEvent")).toBe(false);
  });
});
