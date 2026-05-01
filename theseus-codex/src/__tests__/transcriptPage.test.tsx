import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getFounder: vi.fn(),
  db: {
    upload: { findFirst: vi.fn() },
    conclusion: { findMany: vi.fn() },
  },
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

vi.mock("next/navigation", () => ({
  notFound: vi.fn(() => {
    throw new Error("not found");
  }),
  redirect: vi.fn((path: string) => {
    throw new Error(`redirect:${path}`);
  }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/PublishToToolbar", () => ({
  default: () => <div data-testid="publish-toolbar">Publish to</div>,
}));

vi.mock("@/components/PublishToggle", () => ({
  default: ({ uploadId }: { uploadId: string }) => (
    <button data-testid="publish-toggle" type="button">
      Toggle {uploadId}
    </button>
  ),
}));

vi.mock("@/lib/auth", () => ({
  getFounder: mocks.getFounder,
}));

vi.mock("@/lib/db", () => ({
  db: mocks.db,
}));

import TranscriptPage from "@/app/(authed)/transcripts/[uploadId]/page";

async function renderTranscript(): Promise<string> {
  const element = await TranscriptPage({
    params: Promise.resolve({ uploadId: "upload_fixture" }),
    searchParams: Promise.resolve({}),
  });
  return renderToStaticMarkup(element);
}

describe("TranscriptPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getFounder.mockResolvedValue({
      id: "founder-1",
      organizationId: "org-1",
      role: "admin",
    });
    mocks.db.upload.findFirst.mockResolvedValue({
      id: "upload_fixture",
      title: "Dorkesh-style fixture",
      description: "A fixture transcript.",
      sourceType: "transcript",
      status: "ingested",
      textContent: null,
      blurb:
        "This fixture captures a short conversation about turning raw founder dialogue into an inspectable transcript surface.",
      publishedAt: null,
      slug: null,
      visibility: "org",
      createdAt: new Date("2026-05-01T12:00:00.000Z"),
      founderId: "founder-1",
      founder: { displayName: "Michael Quintin", name: "Michael", username: "mq" },
      chunks: [
        {
          id: "chunk-a",
          index: 0,
          text: "Conversation archives should behave like podcasts with durable citations.",
          startMs: 12_000,
          endMs: null,
          speakerLabel: "Michael",
          headingHint: "Conversation Archive",
        },
        {
          id: "chunk-b",
          index: 1,
          text: "The summary should invite reading without replacing the raw transcript.",
          startMs: 90_000,
          endMs: null,
          speakerLabel: "Ada",
          headingHint: null,
        },
        {
          id: "chunk-c",
          index: 2,
          text: "Stable chunk ids make Oracle citations land on the exact line.",
          startMs: null,
          endMs: null,
          speakerLabel: null,
          headingHint: "Citation Contract",
        },
      ],
    });
    mocks.db.conclusion.findMany.mockResolvedValue([
      {
        id: "conclusion-123456",
        text: "Recorded reasoning is valuable when later readers can inspect the source line.",
        confidenceTier: "firm",
        topicHint: "knowledge",
        rationale: "Anchors preserve inspection context.",
      },
    ]);
  });

  it("snapshots a fixture transcript with timestamps, speakers, and chunk anchors", async () => {
    const html = await renderTranscript();

    expect(html).toMatchSnapshot();
    expect(html).toContain('id="chunk-chunk-a"');
    expect(html).toContain("[00:12]");
    expect(html).toContain("Michael:");
    expect(html).toContain("/transcripts/upload_fixture?anchor=chunk-chunk-c");
  });
});
