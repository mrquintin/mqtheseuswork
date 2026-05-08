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

import ForecastsLayout from "@/app/forecasts/layout";

async function renderLayout(children: ReactNode = <main>Forecast child</main>) {
  const element = await ForecastsLayout({ children });
  return renderToStaticMarkup(element);
}

describe("ForecastsLayout", () => {
  beforeEach(() => {
    mocks.getFounder.mockReset();
    mocks.getFounder.mockResolvedValue(null);
  });

  it("renders PublicHeader around the public Forecasts tree", async () => {
    const html = await renderLayout();

    expect(mocks.getFounder).toHaveBeenCalledTimes(1);
    expect(html).toContain('data-testid="public-header"');
    expect(html).toContain('data-authed="false"');
    expect(html).toContain("Forecast child");
  });

  it("passes an authed PublicHeader state when a founder session exists", async () => {
    mocks.getFounder.mockResolvedValue({ id: "founder-1" });

    const html = await renderLayout();

    expect(html).toContain('data-authed="true"');
  });
});
