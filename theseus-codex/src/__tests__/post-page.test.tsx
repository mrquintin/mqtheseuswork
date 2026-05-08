import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  db: {
    upload: { findFirst: vi.fn() },
    publishedConclusion: { findFirst: vi.fn() },
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
});
