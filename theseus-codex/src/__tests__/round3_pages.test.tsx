import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/auth", () => ({
  getFounder: vi.fn().mockResolvedValue({
    id: "founder-1",
    name: "Test Founder",
    username: "testfounder",
    organizationId: "org-1",
    organization: { slug: "test-org" },
  }),
}));

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  notFound: vi.fn(),
  usePathname: vi.fn().mockReturnValue("/"),
  useRouter: vi.fn().mockReturnValue({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("next/cache", () => ({
  revalidatePath: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string; [k: string]: unknown }) => {
    const { style, className, ...rest } = props as Record<string, unknown>;
    return <a href={href} {...rest}>{children}</a>;
  },
}));

vi.mock("@/lib/api/round3", () => ({
  fetchProvenanceRecords: vi.fn().mockResolvedValue([
    {
      id: "prov-1",
      conclusionId: "conc-1",
      sourceUploadId: "upload-1",
      extractionMethod: "llm_extraction",
      confidence: 0.85,
      chain: [{ step: 0, kind: "source", ref: "upload-1", detail: "Extracted from upload" }],
      createdAt: "2026-01-15T10:00:00Z",
    },
  ]),
  fetchProvenanceForConclusion: vi.fn().mockResolvedValue([]),
  fetchProvenanceForConclusionDiag: vi.fn().mockResolvedValue({
    records: [
      {
        id: "prov-1",
        conclusionId: "conc-1",
        sourceUploadId: "upload-1",
        extractionMethod: "llm_extraction",
        confidence: 0.85,
        chain: [{ step: 0, kind: "source", ref: "upload-1", detail: "Extracted from upload" }],
        createdAt: "2026-01-15T10:00:00Z",
      },
    ],
  }),
  fetchCascade: vi.fn().mockResolvedValue([
    {
      id: "cascade-1",
      conclusionId: "conc-1",
      parentId: null,
      kind: "root",
      label: "Root conclusion",
      confidence: 0.9,
      children: [],
    },
  ]),
  fetchCascadeDiag: vi.fn().mockResolvedValue({
    roots: [
      {
        id: "cascade-1",
        conclusionId: "conc-1",
        parentId: null,
        kind: "root",
        label: "Root conclusion",
        confidence: 0.9,
        children: [],
      },
    ],
  }),
  fetchEvalRuns: vi.fn().mockResolvedValue([
    {
      id: "eval-1",
      name: "Coherence suite",
      status: "passed",
      startedAt: "2026-01-15T10:00:00Z",
      completedAt: "2026-01-15T10:05:00Z",
      summary: "All checks passed",
      passRate: 0.95,
    },
  ]),
  fetchEvalRunDetail: vi.fn().mockResolvedValue({
    id: "eval-1",
    name: "Coherence suite",
    status: "passed",
    startedAt: "2026-01-15T10:00:00Z",
    completedAt: "2026-01-15T10:05:00Z",
    summary: "All checks passed",
    passRate: 0.95,
    cases: [
      {
        id: "case-1",
        input: "test input",
        expected: "expected output",
        actual: "expected output",
        passed: true,
        notes: "",
      },
    ],
  }),
  fetchPostMortems: vi.fn().mockResolvedValue([
    {
      id: "pm-1",
      conclusionId: "conc-1",
      conclusionText: "A retracted conclusion",
      retractedAt: "2026-01-10T10:00:00Z",
      reason: "Evidence disproven",
      rootCause: "Insufficient source validation",
      preventionNotes: "Add multi-source verification",
      founderName: "Test Founder",
    },
  ]),
  fetchPeerReviews: vi.fn().mockResolvedValue([
    {
      id: "review-1",
      conclusionId: "conc-1",
      reviewerName: "Reviewer A",
      verdict: "endorse",
      commentary: "Well-supported conclusion",
      createdAt: "2026-01-15T10:00:00Z",
    },
  ]),
  fetchPeerReviewsDiag: vi.fn().mockResolvedValue({
    records: [
      {
        id: "review-1",
        conclusionId: "conc-1",
        reviewerName: "Reviewer A",
        verdict: "endorse",
        commentary: "Well-supported conclusion",
        findings: [],
        createdAt: "2026-01-15T10:00:00Z",
      },
    ],
  }),
  fetchDecayRecords: vi.fn().mockResolvedValue([
    {
      id: "decay-1",
      conclusionId: "conc-1",
      conclusionText: "A decaying conclusion",
      currentConfidence: 0.72,
      decayRate: 0.001,
      lastValidated: "2026-01-01T00:00:00Z",
      projectedExpiry: "2026-06-01T00:00:00Z",
      status: "decaying",
    },
  ]),
  fetchGateSubmissions: vi.fn().mockResolvedValue([
    {
      id: "gate-1",
      kind: "promotion",
      status: "approved",
      submittedBy: "Test Founder",
      submittedAt: "2026-01-15T10:00:00Z",
      resolvedAt: "2026-01-15T10:05:00Z",
      ledgerEntryId: "ledger-1",
    },
  ]),
  fetchGateDetail: vi.fn().mockResolvedValue({
    id: "gate-1",
    kind: "promotion",
    status: "approved",
    submittedBy: "Test Founder",
    submittedAt: "2026-01-15T10:00:00Z",
    resolvedAt: "2026-01-15T10:05:00Z",
    ledgerEntryId: "ledger-1",
    payload: { conclusionId: "conc-1" },
    reviewNotes: "Looks good",
    overrideReason: null,
  }),
  fetchMethods: vi.fn().mockResolvedValue([
    {
      name: "llm_extraction",
      latestVersion: "1.2.0",
      description: "LLM-based claim extraction",
      status: "active",
      usageCount: 42,
    },
  ]),
  fetchMethodVersion: vi.fn().mockResolvedValue({
    name: "llm_extraction",
    version: "1.2.0",
    description: "LLM-based claim extraction",
    parameters: { model: "gpt-4", temperature: 0.1 },
    changelog: "Added confidence calibration",
    publishedAt: "2026-01-10T10:00:00Z",
    publishedBy: "Test Founder",
  }),
  fetchMethodCandidates: vi.fn().mockResolvedValue([
    {
      id: "cand-1",
      name: "graph_extraction",
      proposedBy: "Test Founder",
      description: "Graph-based extraction method",
      status: "proposed",
      createdAt: "2026-01-12T10:00:00Z",
    },
  ]),
  toCSV: vi.fn().mockReturnValue("id,name\n1,test"),
  downloadHref: vi.fn().mockReturnValue("data:text/csv;charset=utf-8,test"),
}));

import React from "react";

async function renderServerComponent(Component: React.FC<unknown>, props: Record<string, unknown> = {}) {
  const result = await (Component as (props: Record<string, unknown>) => Promise<React.JSX.Element>)(props);
  expect(result).toBeDefined();
  return result;
}

describe("Round 3 pages render without error", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders provenance page", async () => {
    const { default: ProvenancePage } = await import("@/app/(authed)/provenance/page");
    const result = await renderServerComponent(ProvenancePage);
    expect(result).toBeDefined();
  });

  it("renders cascade explorer page", async () => {
    const { default: CascadePage } = await import("@/app/(authed)/cascade/[conclusionId]/page");
    const result = await renderServerComponent(CascadePage, {
      params: Promise.resolve({ conclusionId: "conc-1" }),
    });
    expect(result).toBeDefined();
  });

  it("renders eval page", async () => {
    const { default: EvalPage } = await import("@/app/(authed)/eval/page");
    const result = await renderServerComponent(EvalPage);
    expect(result).toBeDefined();
  });

  it("renders eval run detail page", async () => {
    const { default: EvalRunDetailPage } = await import("@/app/(authed)/eval/runs/[runId]/page");
    const result = await renderServerComponent(EvalRunDetailPage, {
      params: Promise.resolve({ runId: "eval-1" }),
    });
    expect(result).toBeDefined();
  });

  it("renders post-mortem page", async () => {
    const { default: PostMortemPage } = await import("@/app/(authed)/post-mortem/page");
    const result = await renderServerComponent(PostMortemPage);
    expect(result).toBeDefined();
  });

  it("renders peer review page", async () => {
    const { default: PeerReviewPage } = await import("@/app/(authed)/peer-review/[conclusionId]/page");
    const result = await renderServerComponent(PeerReviewPage, {
      params: Promise.resolve({ conclusionId: "conc-1" }),
      searchParams: Promise.resolve({}),
    });
    expect(result).toBeDefined();
  });

  it("renders decay page", async () => {
    const { default: DecayPage } = await import("@/app/(authed)/decay/page");
    const result = await renderServerComponent(DecayPage, {
      searchParams: Promise.resolve({}),
    });
    expect(result).toBeDefined();
  });

  it("renders rigor gate page", async () => {
    const { default: RigorGatePage } = await import("@/app/(authed)/rigor-gate/page");
    const result = await renderServerComponent(RigorGatePage, {
      searchParams: Promise.resolve({}),
    });
    expect(result).toBeDefined();
  });

  it("renders rigor gate detail page", async () => {
    const { default: RigorGateDetailPage } = await import("@/app/(authed)/rigor-gate/[submissionId]/page");
    const result = await renderServerComponent(RigorGateDetailPage, {
      params: Promise.resolve({ submissionId: "gate-1" }),
      searchParams: Promise.resolve({}),
    });
    expect(result).toBeDefined();
  });

  it("renders methods page", async () => {
    const { default: MethodsPage } = await import("@/app/(authed)/methods/page");
    const result = await renderServerComponent(MethodsPage);
    expect(result).toBeDefined();
  });

  it("renders method version page", async () => {
    const { default: MethodVersionPage } = await import("@/app/(authed)/methods/[name]/[version]/page");
    const result = await renderServerComponent(MethodVersionPage, {
      params: Promise.resolve({ name: "llm_extraction", version: "1.2.0" }),
      searchParams: Promise.resolve({}),
    });
    expect(result).toBeDefined();
  });

  it("renders method candidates page", async () => {
    const { default: MethodCandidatesPage } = await import("@/app/(authed)/methods/candidates/page");
    const result = await renderServerComponent(MethodCandidatesPage);
    expect(result).toBeDefined();
  });

  it("renders provenance tab", async () => {
    const { default: ProvenanceTab } = await import("@/app/(authed)/conclusions/[id]/provenance-tab");
    const result = await renderServerComponent(ProvenanceTab, { conclusionId: "conc-1" });
    expect(result).toBeDefined();
  });

  it("renders cascade tab", async () => {
    const { default: CascadeTab } = await import("@/app/(authed)/conclusions/[id]/cascade-tab");
    const result = await renderServerComponent(CascadeTab, { conclusionId: "conc-1" });
    expect(result).toBeDefined();
  });

  it("renders peer review tab", async () => {
    const { default: PeerReviewTab } = await import("@/app/(authed)/conclusions/[id]/peer-review-tab");
    const result = await renderServerComponent(PeerReviewTab, { conclusionId: "conc-1" });
    expect(result).toBeDefined();
  });
});
