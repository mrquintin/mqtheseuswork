import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getFounder: vi.fn(),
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

import CurrentsLayout from "@/app/currents/layout";

async function renderLayout(children: ReactNode = <main>Current child</main>) {
  const element = await CurrentsLayout({ children });
  return renderToStaticMarkup(element);
}

describe("CurrentsLayout", () => {
  beforeEach(() => {
    mocks.getFounder.mockReset();
    mocks.getFounder.mockResolvedValue(null);
  });

  it("renders PublicHeader around the public Currents tree", async () => {
    const html = await renderLayout();

    expect(mocks.getFounder).toHaveBeenCalledTimes(1);
    expect(html).toContain('data-testid="public-header"');
    expect(html).toContain('data-authed="false"');
    expect(html).toContain("Current child");
  });

  it("passes an authed PublicHeader state when a founder session exists", async () => {
    mocks.getFounder.mockResolvedValue({ id: "founder-1" });

    const html = await renderLayout();

    expect(html).toContain('data-authed="true"');
  });
});
