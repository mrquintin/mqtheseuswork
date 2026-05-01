import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const dbMock = vi.hoisted(() => ({
  founder: {
    findMany: vi.fn(),
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

vi.mock("@/components/PublicHeader", () => ({
  default: ({ authed }: { authed: boolean }) => (
    <header data-authed={String(authed)}>Public header</header>
  ),
}));

vi.mock("@/lib/db", () => ({
  db: dbMock,
}));

import AboutPage from "@/app/about/page";

const originalHideMembers = process.env.NEXT_PUBLIC_ABOUT_HIDE_MEMBERS;

function founderFixture() {
  return [
    {
      id: "founder-1",
      name: "Founder One",
      displayName: "Ada Quint",
      roleTitle: "Research Partner",
      bio: "Builds the Codex method layer and turns recorded deliberation into public theses.",
      publicUrl: "https://www.linkedin.com/in/ada-quint",
    },
    {
      id: "founder-2",
      name: "Byron Vale",
      displayName: null,
      roleTitle: null,
      bio: "Studies prediction-market structure and the translation from conviction to priced belief.",
      publicUrl: null,
    },
    {
      id: "founder-3",
      name: "Founder Three",
      displayName: "Omitted Founder",
      roleTitle: "Internal Role",
      bio: null,
      publicUrl: "https://example.com/omitted",
    },
  ];
}

async function renderAboutPage(): Promise<string> {
  const element = await AboutPage();
  return renderToStaticMarkup(element);
}

describe("AboutPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete process.env.NEXT_PUBLIC_ABOUT_HIDE_MEMBERS;
    dbMock.founder.findMany.mockResolvedValue(founderFixture());
  });

  afterEach(() => {
    if (originalHideMembers == null) {
      delete process.env.NEXT_PUBLIC_ABOUT_HIDE_MEMBERS;
    } else {
      process.env.NEXT_PUBLIC_ABOUT_HIDE_MEMBERS = originalHideMembers;
    }
  });

  it("snapshots the public about page with visible founder cards", async () => {
    const html = await renderAboutPage();

    expect(html).toMatchSnapshot();
    expect(html).toContain("Ada Quint");
    expect(html).toContain("Byron Vale");
    expect(html).not.toContain("Omitted Founder");
    expect(html).not.toContain("Internal Role");
  });

  it("snapshots the public about page with member anonymity enabled", async () => {
    process.env.NEXT_PUBLIC_ABOUT_HIDE_MEMBERS = "true";

    const html = await renderAboutPage();

    expect(html).toMatchSnapshot();
    expect(html).toContain(
      "The firm currently maintains member anonymity. Reach out via the contact below.",
    );
    expect(html).not.toContain("Ada Quint");
    expect(dbMock.founder.findMany).not.toHaveBeenCalled();
  });
});
