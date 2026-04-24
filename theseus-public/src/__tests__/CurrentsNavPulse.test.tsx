// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

const pathnameMock = vi.fn<() => string | null>(() => "/");

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameMock(),
}));

import { CurrentsNavPulse } from "@/components/CurrentsNavPulse";

afterEach(() => {
  cleanup();
  pathnameMock.mockReset();
  pathnameMock.mockImplementation(() => "/");
});

describe("CurrentsNavPulse", () => {
  it("renders a link to /currents with no active styling on the index route", () => {
    pathnameMock.mockImplementation(() => "/");
    const { container } = render(<CurrentsNavPulse />);
    const link = container.querySelector("a");
    expect(link).not.toBeNull();
    expect(link!.getAttribute("href")).toBe("/currents");
    expect(link!.textContent).toContain("Current events");
    // No active gold color applied.
    expect(link!.style.color).toBe("");
    expect(link!.style.fontWeight).toBe("");
  });

  it("applies active styling when the path starts with /currents", () => {
    pathnameMock.mockImplementation(() => "/currents");
    const { container } = render(<CurrentsNavPulse />);
    const link = container.querySelector("a");
    expect(link).not.toBeNull();
    // Either color or weight proves the "active" branch fired.
    const isActive =
      link!.style.color.includes("212") ||
      link!.style.color.toLowerCase() === "#d4a017" ||
      link!.style.fontWeight === "600";
    expect(isActive).toBe(true);
  });

  it("applies active styling for nested currents paths", () => {
    pathnameMock.mockImplementation(() => "/currents/op-abc");
    const { container } = render(<CurrentsNavPulse />);
    const link = container.querySelector("a");
    const isActive =
      link!.style.color.includes("212") ||
      link!.style.color.toLowerCase() === "#d4a017" ||
      link!.style.fontWeight === "600";
    expect(isActive).toBe(true);
  });
});
