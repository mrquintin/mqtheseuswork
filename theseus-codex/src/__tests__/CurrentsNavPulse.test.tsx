import { describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";
import { usePathname } from "next/navigation";
import { CurrentsNavPulse } from "@/components/CurrentsNavPulse";

vi.mock("next/navigation", () => ({
  usePathname: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: {
    children: ReactNode;
    href: string;
    [key: string]: unknown;
  }) => <a href={href} {...props}>{children}</a>,
}));

type ElementNode = ReactElement<{
  [key: string]: unknown;
  children?: ReactNode;
  href?: string;
  style?: Record<string, unknown>;
}>;

function isElement(node: ReactNode): node is ElementNode {
  return (
    typeof node === "object" &&
    node !== null &&
    "props" in (node as object) &&
    "type" in (node as object)
  );
}

function flattenChildren(children: ReactNode): ReactNode[] {
  if (children === null || children === undefined || children === false) {
    return [];
  }
  if (Array.isArray(children)) {
    return children.flatMap(flattenChildren);
  }
  return [children];
}

function findByClassName(root: ReactNode, className: string): ElementNode | null {
  const stack = flattenChildren(root);
  while (stack.length) {
    const node = stack.shift();
    if (!isElement(node)) continue;
    if (node.props.className === className) return node;
    stack.unshift(...flattenChildren(node.props.children));
  }
  return null;
}

describe("CurrentsNavPulse", () => {
  it("renders the Current events link with a pure CSS pulse dot", () => {
    vi.mocked(usePathname).mockReturnValue("/");

    const element = CurrentsNavPulse() as ElementNode;

    expect(element.props.href).toBe("/currents");
    expect(element.props["aria-label"]).toBe("Current events — live");
    expect(flattenChildren(element.props.children)).toContain("Current events");
    expect(findByClassName(element.props.children, "currents-pulse")).not.toBeNull();
  });

  it("sets active styling when the pathname starts with /currents", () => {
    vi.mocked(usePathname).mockReturnValue("/currents/topic/markets");

    const element = CurrentsNavPulse() as ElementNode;

    expect(element.props.style).toMatchObject({
      color: "var(--currents-gold)",
      fontWeight: 600,
    });
  });
});
