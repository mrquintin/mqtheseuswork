import type { ReactElement, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const dbMock = vi.hoisted(() => ({
  publicResponse: {
    findMany: vi.fn(),
    updateMany: vi.fn(),
  },
}));

const tenantMock = vi.hoisted(() => ({
  requireTenantContext: vi.fn(),
}));

const cacheMock = vi.hoisted(() => ({
  revalidatePath: vi.fn(),
}));

vi.mock("@/lib/db", () => ({
  db: dbMock,
}));

vi.mock("@/lib/tenant", () => tenantMock);

vi.mock("next/cache", () => cacheMock);

import ResponsesInboxPage from "@/app/(authed)/responses/page";
import { markPublicResponseSeen } from "@/app/(authed)/responses/actions";

type ElementNode = ReactElement<{
  [key: string]: unknown;
  children?: ReactNode;
  className?: string;
}>;

const tenant = {
  organizationId: "org-1",
  organizationSlug: "theseus-local",
  founderId: "founder-1",
  founderName: "alpha",
  founderUsername: "alpha",
  role: "admin",
};

const responseRow = {
  id: "resp-1",
  kind: "counter_argument",
  body: "This is a sufficiently detailed public response that should appear in the founder inbox.",
  citationUrl: "https://example.com/source",
  submitterEmail: "reader@example.com",
  orcid: "",
  pseudonymous: false,
  status: "pending",
  createdAt: new Date("2026-05-08T12:00:00.000Z"),
  seenAt: null,
  published: {
    slug: "falsifiable-inference",
    version: 1,
    payloadJson: JSON.stringify({
      conclusionText: "Inference should stay falsifiable",
    }),
  },
};

describe("founder responses inbox", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    tenantMock.requireTenantContext.mockResolvedValue(tenant);
    dbMock.publicResponse.findMany.mockResolvedValue([responseRow]);
    dbMock.publicResponse.updateMany.mockResolvedValue({ count: 1 });
  });

  it("renders an unseen badge when rows exist with seenAt null", async () => {
    const element = await ResponsesInboxPage();
    const text = flattenText(element).join(" ");

    expect(text).toMatch(/1\s+unseen/);
    expect(findByClassName(element, "currents-pulse")).not.toBeNull();
  });

  it("the Mark seen action stamps seenAt", async () => {
    const formData = new FormData();
    formData.set("id", "resp-1");
    formData.set("seen", "false");

    await markPublicResponseSeen(formData);

    expect(dbMock.publicResponse.updateMany).toHaveBeenCalledWith({
      where: {
        id: "resp-1",
        organizationId: "org-1",
      },
      data: {
        seenAt: expect.any(Date),
      },
    });
    expect(cacheMock.revalidatePath).toHaveBeenCalledWith("/responses");
  });
});

function isElement(node: ReactNode): node is ElementNode {
  return (
    typeof node === "object" &&
    node !== null &&
    "props" in (node as object) &&
    "type" in (node as object)
  );
}

function childrenOf(node: ReactNode): ReactNode[] {
  if (node === null || node === undefined || node === false) return [];
  if (Array.isArray(node)) return node.flatMap(childrenOf);
  if (isElement(node)) return childrenOf(node.props.children);
  return [node];
}

function flattenText(node: ReactNode): string[] {
  if (typeof node === "string" || typeof node === "number") return [String(node)];
  if (!isElement(node)) {
    return childrenOf(node).flatMap(flattenText);
  }
  return childrenOf(node.props.children).flatMap(flattenText);
}

function findByClassName(root: ReactNode, className: string): ElementNode | null {
  const stack = nodeList(root);
  while (stack.length) {
    const node = stack.shift();
    if (!isElement(node)) continue;
    if (node.props.className === className) return node;
    stack.unshift(...nodeList(node.props.children));
  }
  return null;
}

function nodeList(node: ReactNode): ReactNode[] {
  if (node === null || node === undefined || node === false) return [];
  if (Array.isArray(node)) return node.flatMap(nodeList);
  return [node];
}
