import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

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
  usePathname: () => "/",
}));

vi.mock("@/components/ThemeToggle", () => ({
  default: () => <button aria-label="Theme toggle" type="button" />,
}));

import PublicHeader from "@/components/PublicHeader";

function renderHeader(authed: boolean): string {
  return renderToStaticMarkup(<PublicHeader authed={authed} />);
}

function publicNav(html: string): string {
  const match = html.match(
    /<nav\b[^>]*aria-label="Public navigation"[\s\S]*?<\/nav>/,
  );
  expect(match).not.toBeNull();
  return match![0];
}

describe("PublicHeader", () => {
  it("renders a Home link before About in the public nav", () => {
    const nav = publicNav(renderHeader(false));
    const homeIndex = nav.indexOf(">Home</a>");
    const aboutIndex = nav.indexOf(">About</a>");

    expect(homeIndex).toBeGreaterThanOrEqual(0);
    expect(aboutIndex).toBeGreaterThan(homeIndex);
  });

  it("does not render a Responses link in the public nav", () => {
    const nav = publicNav(renderHeader(false));

    expect(nav).not.toContain('href="/responses"');
    expect(nav).not.toContain(">Responses</a>");
  });

  it("renders the authed founder portal affordance at /dashboard", () => {
    const html = renderHeader(true);

    expect(html).toContain('href="/dashboard"');
    expect(html).toContain("Founder Portal →");
    expect(html).not.toContain("Dashboard →");
  });

  it("keeps the unauthenticated founder login affordance", () => {
    const html = renderHeader(false);

    expect(html).toContain('href="/login"');
    expect(html).toContain("Founder login →");
  });
});
