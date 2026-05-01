import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const navMocks = vi.hoisted(() => ({
  pathname: "/dashboard",
  push: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navMocks.pathname,
  useRouter: () => ({
    push: navMocks.push,
    refresh: navMocks.refresh,
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

vi.mock("@/components/ThemeToggle", () => ({
  default: () => <button aria-label="Theme toggle" type="button" />,
}));

vi.mock("@/components/LabyrinthIcon", () => ({
  default: () => <span aria-hidden="true">LABYRINTH</span>,
}));

import Nav from "@/components/Nav";

function founder(role: string) {
  return {
    name: "Ada Quint",
    username: "ada",
    organizationSlug: "theseus-local",
    role,
  };
}

describe("Nav", () => {
  beforeEach(() => {
    navMocks.pathname = "/dashboard";
    navMocks.push.mockReset();
    navMocks.refresh.mockReset();
  });

  it("snapshots the consolidated top nav for an admin", () => {
    const html = renderToStaticMarkup(<Nav founder={founder("admin")} />);
    expect(html).toMatchSnapshot();
  });

  it("snapshots the consolidated top nav for a non-admin founder", () => {
    const html = renderToStaticMarkup(<Nav founder={founder("founder")} />);
    expect(html).toMatchSnapshot();
  });
});
