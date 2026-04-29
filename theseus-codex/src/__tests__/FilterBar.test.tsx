import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";

import {
  FilterBarView,
  createDebouncedSearchUpdater,
  replaceFilterUrl,
} from "@/app/currents/FilterBar";
import { DEFAULT_FILTER, type Filter } from "@/lib/filterMatch";

vi.mock("next/navigation", () => ({
  usePathname: vi.fn(),
  useRouter: vi.fn(),
  useSearchParams: vi.fn(),
}));

type ElementNode = ReactElement<{
  [key: string]: unknown;
  children?: ReactNode;
  onClick?: () => void;
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
  if (children === null || children === undefined || children === false) return [];
  if (Array.isArray(children)) return children.flatMap(flattenChildren);
  return [children];
}

function textContent(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isElement(node)) return "";
  return flattenChildren(node.props.children).map(textContent).join("");
}

function findButton(root: ReactNode, label: string): ElementNode | null {
  const stack = flattenChildren(root);

  while (stack.length) {
    const node = stack.shift();
    if (!isElement(node)) continue;
    if (node.type === "button" && textContent(node.props.children) === label) {
      return node;
    }
    stack.unshift(...flattenChildren(node.props.children));
  }

  return null;
}

function renderFilterBarView(filter: Filter, onFilterChange = vi.fn()) {
  return FilterBarView({
    filter,
    onFilterChange,
    onSearchChange: vi.fn(),
    searchValue: filter.q,
    topics: ["markets", "policy"],
  });
}

describe("FilterBar", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("toggles stance chips on and off", () => {
    const addStance = vi.fn();
    const emptyView = renderFilterBarView(DEFAULT_FILTER, addStance);
    findButton(emptyView, "disagrees")?.props.onClick?.();

    expect(addStance).toHaveBeenCalledWith({
      ...DEFAULT_FILTER,
      stance: ["disagrees"],
    });

    const removeStance = vi.fn();
    const activeView = renderFilterBarView(
      { ...DEFAULT_FILTER, stance: ["disagrees"] },
      removeStance,
    );
    findButton(activeView, "disagrees")?.props.onClick?.();

    expect(removeStance).toHaveBeenCalledWith({
      ...DEFAULT_FILTER,
      stance: [],
    });
  });

  it("updates the URL without scrolling when filters change", () => {
    const router = { replace: vi.fn() };

    replaceFilterUrl(router, "/currents", {
      ...DEFAULT_FILTER,
      stance: ["disagrees"],
      since: "24h",
    });

    expect(router.replace).toHaveBeenCalledWith(
      "/currents?stance=disagrees&since=24h",
      { scroll: false },
    );
  });

  it("debounces search URL updates by 250ms", () => {
    vi.useFakeTimers();
    const router = { replace: vi.fn() };
    let currentFilter = DEFAULT_FILTER;
    const updater = createDebouncedSearchUpdater(
      () => currentFilter,
      (nextFilter) => {
        currentFilter = nextFilter;
        replaceFilterUrl(router, "/currents", nextFilter);
      },
    );

    updater.queue("markets");
    vi.advanceTimersByTime(249);
    expect(router.replace).not.toHaveBeenCalled();

    updater.queue("energy");
    vi.advanceTimersByTime(249);
    expect(router.replace).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(router.replace).toHaveBeenCalledTimes(1);
    expect(router.replace).toHaveBeenCalledWith("/currents?q=energy", {
      scroll: false,
    });
  });
});
