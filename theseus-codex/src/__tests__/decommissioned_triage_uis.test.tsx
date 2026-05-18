import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Decommissioned triage UIs (2026-05-17).
 *
 * `/(authed)/extractor/re-extract` and `/(authed)/principles/queue`
 * used to surface founder-actionable triage rows. Principle
 * distillation is now auto-accept on extraction
 * (`auto_accept_principles_2026_05_17`), so both pages were repurposed
 * as READ-ONLY audit logs. These tests pin that they:
 *
 *   - render with HTTP-200 shape (no thrown redirects, valid markup),
 *   - carry the new title copy,
 *   - render no Accept / Reject / Edit / Merge buttons,
 *   - issue no `<form action=…>` or interactive buttons (textarea
 *     / checkbox / select).
 */

const dbMock = vi.hoisted(() => ({
  conclusion: { findMany: vi.fn() },
  principle: { findMany: vi.fn() },
}));

const tenantMock = vi.hoisted(() => ({
  requireTenantContext: vi.fn(),
}));

vi.mock("@/lib/db", () => ({ db: dbMock }));
vi.mock("@/lib/tenant", () => tenantMock);

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  redirect: (target: string) => {
    throw new Error(`redirect(${target})`);
  },
}));

const TENANT = {
  organizationId: "org-1",
  organizationSlug: "theseus-local",
  founderId: "founder-1",
  founderName: "alpha",
  founderUsername: "alpha",
  role: "admin" as const,
};

function principleRow(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "principle-1",
    organizationId: "org-1",
    text: "Methods that beat predict-the-mean must beat it after costs.",
    domainsJson: JSON.stringify(["forecasting"]),
    clusterConclusionIds: JSON.stringify(["c1"]),
    citedConclusionIds: JSON.stringify(["c1"]),
    status: "accepted",
    triageReason: "",
    mergedIntoId: null,
    convictionScore: 0.72,
    domainBreadth: 1,
    clusterCentroidSimilarity: 0.81,
    publicVisible: true,
    driftReason: null,
    reviewedAt: new Date("2026-05-15T00:00:00Z"),
    publishedAt: new Date("2026-05-15T00:00:00Z"),
    createdAt: new Date("2026-05-15T00:00:00Z"),
    updatedAt: new Date("2026-05-15T00:00:00Z"),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  tenantMock.requireTenantContext.mockResolvedValue(TENANT);
});

describe("extraction audit log (formerly /extractor/re-extract)", () => {
  it("renders with the new title, banner, and no actionable buttons", async () => {
    dbMock.conclusion.findMany.mockResolvedValue([
      {
        id: "conclusion-1",
        text: "We tend to underprice tail risk in single-shot bets.",
        sourceSpan: "we always underprice tail risk",
        rationale: null,
        createdAt: new Date("2026-05-10T00:00:00Z"),
      },
    ]);

    const { default: Page } = await import(
      "@/app/(authed)/extractor/re-extract/page"
    );
    const element = await Page();
    const html = renderToStaticMarkup(element);

    expect(html).toContain("Extraction audit log");
    expect(html).toContain("Principle extraction is automatic");
    expect(html).toContain('data-testid="extraction-audit-log"');
    expect(html).toContain("conclusion-1".slice(0, 8));
    // No mutating UI affordances.
    expect(html).not.toMatch(/<button[^>]*>/i);
    expect(html).not.toMatch(/<textarea/i);
    expect(html).not.toMatch(/<form[^>]*action=/i);
    expect(html.toLowerCase()).not.toContain(">accept<");
    expect(html.toLowerCase()).not.toContain(">reject<");
    expect(html.toLowerCase()).not.toContain(">merge<");
  });

  it("renders a non-empty empty-state when no first-person rows match", async () => {
    dbMock.conclusion.findMany.mockResolvedValue([
      {
        id: "conclusion-2",
        text: "A principle-shaped statement, third-person already.",
        sourceSpan: "",
        rationale: null,
        createdAt: new Date("2026-05-11T00:00:00Z"),
      },
    ]);

    const { default: Page } = await import(
      "@/app/(authed)/extractor/re-extract/page"
    );
    const element = await Page();
    const html = renderToStaticMarkup(element);

    expect(html).toContain("Extraction audit log");
    expect(html).toMatch(/No first-person conclusions/i);
  });
});

describe("recent principles (formerly /principles/queue)", () => {
  it("renders the new title and no triage buttons", async () => {
    dbMock.principle.findMany.mockResolvedValue([
      principleRow(),
      principleRow({ id: "principle-2", text: "Another principle." }),
    ]);

    const { default: Page } = await import(
      "@/app/(authed)/principles/queue/page"
    );
    const element = await Page();
    const html = renderToStaticMarkup(element);

    expect(html).toContain("Recent principles");
    expect(html).toContain("Principle distillation is automatic");
    expect(html).toContain('data-testid="recent-principles"');
    // Rows present and link to canonical detail (NOT to /triage).
    expect(html).toContain('href="/principles/principle-1"');
    expect(html).not.toMatch(/href="\/principles\/[^"]*\/triage"/);
    // No mutating affordances.
    expect(html).not.toMatch(/<button[^>]*>/i);
    expect(html).not.toMatch(/<textarea/i);
    expect(html).not.toMatch(/<select/i);
    expect(html).not.toMatch(/<form[^>]*action=/i);
    expect(html.toLowerCase()).not.toContain("triage queue");
  });

  it("uses createdAt-desc ordering with no status filter", async () => {
    const findManySpy = dbMock.principle.findMany.mockResolvedValue([
      principleRow({ status: "rejected" }),
    ]);

    const { default: Page } = await import(
      "@/app/(authed)/principles/queue/page"
    );
    await Page();

    expect(findManySpy).toHaveBeenCalled();
    const args = findManySpy.mock.calls[0]?.[0] ?? {};
    expect(args).toMatchObject({
      where: { organizationId: TENANT.organizationId },
      orderBy: { createdAt: "desc" },
    });
    // No status filter — rejected rows are still surfaced as audit.
    expect((args.where ?? {}).status).toBeUndefined();
  });
});
