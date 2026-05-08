import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PublicOpinion, PublicSource } from "@/lib/currentsTypes";

const mocks = vi.hoisted(() => ({
  getFounder: vi.fn(),
}));

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

vi.mock("@/components/PublicHeader", () => ({
  default: ({ authed }: { authed: boolean }) => (
    <header data-authed={String(authed)} data-testid="public-header">
      Public header
    </header>
  ),
}));

vi.mock("@/lib/auth", () => ({
  getFounder: mocks.getFounder,
}));

vi.mock("@/app/currents/[id]/CopyLinkButton", () => ({
  CopyLinkButton: ({ opinionId }: { opinionId: string }) => (
    <button type="button">Copy {opinionId}</button>
  ),
}));

vi.mock("@/app/currents/[id]/FollowupChat", () => ({
  default: ({ opinionId }: { opinionId: string }) => (
    <section aria-label="Follow-up">Follow-up {opinionId}</section>
  ),
}));

import CurrentsLayout from "@/app/currents/layout";
import DetailClient from "@/app/currents/[id]/DetailClient";

function opinion(overrides: Partial<PublicOpinion> = {}): PublicOpinion {
  return {
    id: "opinion-1",
    organization_id: "org-1",
    event_id: "event-1",
    stance: "complicates",
    confidence: 0.72,
    headline: "Markets misread the signal",
    body_markdown: "The firm leans on one stored conclusion.",
    uncertainty_notes: [],
    topic_hint: "markets",
    model_name: "test-model",
    generated_at: "2026-04-29T12:00:00.000Z",
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: null,
    citations: [],
    ...overrides,
  };
}

function source(overrides: Partial<PublicSource> = {}): PublicSource {
  return {
    id: "source-row-1",
    opinion_id: "opinion-1",
    source_kind: "conclusion",
    source_id: "conclusion-1",
    source_text: "Stored firm reasoning belongs in a reader-safe source row.",
    quoted_span: "reader-safe source row",
    retrieval_score: 0.91,
    is_revoked: false,
    revoked_reason: null,
    canonical_path: "/c/conclusion-1",
    ...overrides,
  };
}

async function renderChrome() {
  const detail = (
    <DetailClient opinion={opinion()} sources={[source()]} />
  );
  const element = await CurrentsLayout({ children: detail });
  return renderToStaticMarkup(element);
}

describe("Currents detail chrome", () => {
  beforeEach(() => {
    mocks.getFounder.mockReset();
    mocks.getFounder.mockResolvedValue(null);
  });

  it("renders the public header and detail back link", async () => {
    const html = await renderChrome();

    expect(html).toContain('data-testid="public-header"');
    expect(html).toContain('href="/currents"');
    expect(html).toContain("← Currents");
  });

  it("does not mount founder-publish, rationale-drawer, or audit chrome", async () => {
    const html = await renderChrome();

    expect(html).not.toContain("Publish to");
    expect(html).not.toContain("Rationale drawer");
    expect(html).not.toContain("Audit trail");
    expect(html).not.toContain("Internal rationale");
    expect(html).not.toContain("Open in drawer");
    expect(html).not.toContain("#src-");
  });
});
