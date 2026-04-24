import { describe, it, expect } from "vitest";
import UploadStatusBadge from "@/components/UploadStatusBadge";
import {
  PULSING_STATUSES,
  STATUS_LABEL,
  STATUS_TOOLTIP,
  UPLOAD_STATUSES,
} from "@/lib/uploadStatus";
import type { ReactElement, ReactNode } from "react";

/**
 * The badge is a pure server component — calling it as a function
 * yields the JSX tree we can inspect. The tests don't need jsdom
 * because we're only asserting on React element props, not on
 * rendered DOM.
 */

type ElementNode = ReactElement<{ [key: string]: unknown; children?: ReactNode }>;

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

function findByPredicate(
  root: ReactNode,
  pred: (n: ElementNode) => boolean,
): ElementNode | null {
  const stack = flattenChildren(root);
  while (stack.length) {
    const node = stack.shift();
    if (!isElement(node)) continue;
    if (pred(node)) return node;
    const kids = flattenChildren(node.props.children);
    stack.unshift(...kids);
  }
  return null;
}

describe("UploadStatusBadge", () => {
  it("renders a human label for each known status", () => {
    for (const status of UPLOAD_STATUSES) {
      const el = UploadStatusBadge({ status }) as ElementNode;
      const labelText = flattenChildren(el.props.children)
        .filter((n) => typeof n === "string")
        .join("");
      expect(labelText).toContain(STATUS_LABEL[status]);
    }
  });

  it("sets the canonical tooltip on the pill", () => {
    for (const status of UPLOAD_STATUSES) {
      const el = UploadStatusBadge({ status }) as ElementNode;
      expect(el.props.title).toBe(STATUS_TOOLTIP[status]);
      expect(el.props["data-status"]).toBe(status);
    }
  });

  it("includes a pulse dot only for non-terminal statuses", () => {
    for (const status of UPLOAD_STATUSES) {
      const el = UploadStatusBadge({ status }) as ElementNode;
      const dot = findByPredicate(
        el,
        (n) => (n.props as { ["data-testid"]?: string })["data-testid"] === "status-pulse-dot",
      );
      if (PULSING_STATUSES.has(status)) {
        expect(dot, `expected pulse dot for ${status}`).not.toBeNull();
        expect(el.props["data-pulsing"]).toBe("1");
      } else {
        expect(dot, `expected no pulse dot for ${status}`).toBeNull();
        expect(el.props["data-pulsing"]).toBe("0");
      }
    }
  });

  it("normalizes unknown statuses to 'pending'", () => {
    const el = UploadStatusBadge({ status: "queued_offline" }) as ElementNode;
    expect(el.props["data-status"]).toBe("pending");
    expect(el.props.title).toBe(STATUS_TOOLTIP.pending);
  });
});
