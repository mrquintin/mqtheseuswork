import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  db: {
    upload: { findFirst: vi.fn() },
    publishedConclusion: { findFirst: vi.fn() },
    publicationSignature: { findFirst: vi.fn() },
  },
  getFounder: vi.fn(),
  notFound: vi.fn(() => {
    throw new Error("not found");
  }),
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
  notFound: mocks.notFound,
}));

vi.mock("@/components/PublicHeader", () => ({
  default: ({ authed }: { authed: boolean }) => (
    <header data-authed={String(authed)}>Public header</header>
  ),
}));

vi.mock("@/components/RespondCallout", () => ({
  default: () => <aside data-testid="respond-callout" />,
}));

vi.mock("./ReaderResponses", () => ({
  default: () => <div data-testid="reader-responses" />,
}));

vi.mock("@/app/post/[slug]/ReaderResponses", () => ({
  default: () => <div data-testid="reader-responses" />,
}));

vi.mock("@/components/PrintButton", () => ({
  default: ({
    className,
    label = "PDF",
  }: {
    className?: string;
    label?: string;
  }) => (
    <button
      className={`no-print ${className ?? ""}`.trim()}
      data-testid="print-button"
      type="button"
    >
      {label}
    </button>
  ),
}));

vi.mock("@/lib/auth", () => ({
  getFounder: mocks.getFounder,
}));

vi.mock("@/lib/db", () => ({
  db: mocks.db,
}));

import PostPage from "@/app/post/[slug]/page";

describe("PostPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getFounder.mockResolvedValue(null);
    mocks.db.publishedConclusion.findFirst.mockResolvedValue(null);
    mocks.db.publicationSignature.findFirst.mockResolvedValue(null);
  });

  it("preserves the stored title text and justifies the article body container", async () => {
    const title = "Mixed Case Title Should Stay Mixed Case";
    mocks.db.upload.findFirst.mockResolvedValue({
      id: "post-1",
      organizationId: "org-1",
      title,
      slug: "mixed-case-title",
      description: "",
      authorBio: "Theseus",
      blogExcerpt: "",
      textContent:
        "The first paragraph is deliberately long enough to read as article prose rather than a short label.\n\nThe second paragraph keeps the rendered article body on the public page.",
      publishedAt: new Date("2026-05-01T12:00:00.000Z"),
      sourceType: "written",
      audioUrl: null,
      audioDurationSec: null,
      founder: { displayName: "Theseus", name: "Theseus", username: "theseus" },
    });

    const element = await PostPage({
      params: Promise.resolve({ slug: "mixed-case-title" }),
    });
    const html = renderToStaticMarkup(element);
    const h1 = html.match(/<h1([^>]*)>([^<]*)<\/h1>/);

    expect(h1?.[2]).toBe(title);
    expect(h1?.[1]).not.toContain("Cinzel");
    expect(h1?.[1]).not.toContain("text-transform");
    expect(html).toContain('class="post-body public-article-body"');
  });

  it("renders the print-only metadata block and a no-print toolbar", async () => {
    mocks.db.upload.findFirst.mockResolvedValue({
      id: "post-2",
      organizationId: "org-1",
      title: "Print Snapshot Article",
      slug: "print-snapshot-article",
      description: "",
      authorBio: "Theseus",
      blogExcerpt: "",
      textContent: "Body paragraph one.\n\nBody paragraph two.",
      publishedAt: new Date("2026-05-01T12:00:00.000Z"),
      sourceType: "written",
      audioUrl: null,
      audioDurationSec: null,
      founder: { displayName: "Theseus", name: "Theseus", username: "theseus" },
    });
    mocks.db.publicationSignature.findFirst.mockResolvedValue({
      keyFingerprint: "fp-fixture-1234",
    });

    const element = await PostPage({
      params: Promise.resolve({ slug: "print-snapshot-article" }),
    });
    const html = renderToStaticMarkup(element);

    // Metadata block is in the DOM with the expected fields.
    expect(html).toContain('data-testid="print-metadata-block"');
    expect(html).toContain('class="print-only print-metadata-block"');
    expect(html).toContain("Print Snapshot Article");
    expect(html).toContain("fp-fixture-1234");
    expect(html).toContain("/post/print-snapshot-article");

    // Print button (a toolbar control) is present but tagged no-print.
    // Attribute order is implementation-defined, so just check both
    // are present on the same tag.
    expect(html).toContain('data-testid="print-button"');
    const printButtonTag = html.match(/<button[^>]*data-testid="print-button"[^>]*>/);
    expect(printButtonTag).not.toBeNull();
    expect(printButtonTag![0]).toMatch(/class="[^"]*\bno-print\b/);

    // The "Back to index" toolbar wrapper is no-print so the printed
    // page does not carry it.
    expect(html).toMatch(/class="no-print"[^>]*>[\s\S]*Back to index/);
  });
});
