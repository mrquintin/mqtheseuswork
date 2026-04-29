import React, { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getFounder } from "@/lib/auth";
import { listCurrents } from "@/lib/currentsApi";
import { db } from "@/lib/db";
import type { PublicOpinion } from "@/lib/currentsTypes";
import PublicBlogIndex from "@/app/page";

vi.mock("@/lib/currentsApi", () => ({
  listCurrents: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({
  getFounder: vi.fn(),
}));

vi.mock("@/lib/db", () => ({
  db: {
    upload: {
      findMany: vi.fn(),
    },
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

function opinion(index: number): PublicOpinion {
  return {
    id: `opinion-${index}`,
    organization_id: "org-1",
    event_id: `event-${index}`,
    stance: "complicates",
    confidence: 0.72,
    headline: `Opinion headline ${index}`,
    body_markdown: "Body",
    uncertainty_notes: [],
    topic_hint: index === 2 ? null : "markets",
    model_name: "claude-haiku-4-5",
    generated_at: "2026-04-29T12:00:00.000Z",
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: {
      id: `event-${index}`,
      source: "X",
      external_id: `external-${index}`,
      author_handle: "analyst",
      text: "event text",
      url: "https://example.com/event",
      captured_at: "2026-04-29T12:00:00.000Z",
      observed_at: "2026-04-29T11:59:00.000Z",
      topic_hint: "policy",
    },
    citations: [],
  };
}

type ElementProps = {
  children?: ReactNode;
  [key: string]: unknown;
};

async function resolveAsyncServerComponents(node: ReactNode): Promise<ReactNode> {
  if (Array.isArray(node)) {
    const resolved = await Promise.all(node.map(resolveAsyncServerComponents));
    return resolved.some((child, index) => child !== node[index]) ? resolved : node;
  }

  if (!React.isValidElement(node)) return node;

  if (
    typeof node.type === "function" &&
    node.type.constructor.name === "AsyncFunction"
  ) {
    const rendered = await (node.type as (props: ElementProps) => Promise<ReactNode>)(
      node.props as ElementProps,
    );
    return resolveAsyncServerComponents(rendered);
  }

  const props = node.props as ElementProps;
  if (!("children" in props)) return node;

  const children = await resolveAsyncServerComponents(props.children);
  if (children === props.children) return node;
  if (Array.isArray(children)) return React.cloneElement(node, undefined, ...children);
  return React.cloneElement(node, undefined, children);
}

async function renderHomepage() {
  const element = await PublicBlogIndex();
  const resolved = await resolveAsyncServerComponents(element);
  return renderToStaticMarkup(<>{resolved}</>);
}

describe("CurrentsTeaser", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getFounder).mockResolvedValue(null);
    vi.mocked(db.upload.findMany).mockResolvedValue([]);
  });

  it("renders three compact rows and a See all link", async () => {
    vi.mocked(listCurrents).mockResolvedValueOnce({
      items: [opinion(1), opinion(2), opinion(3)],
    });

    const html = await renderHomepage();

    expect(listCurrents).toHaveBeenCalledWith({ limit: 3 });
    expect((html.match(/<li/g) || []).length).toBe(3);
    expect(html).toContain('href="/currents"');
    expect(html).toContain("See all");
    expect(html).toContain("Opinion headline 1");
    expect(html).toContain("Opinion headline 2");
    expect(html).toContain("Opinion headline 3");
  });

  it("returns null when listCurrents rejects", async () => {
    vi.mocked(listCurrents).mockRejectedValueOnce(new Error("backend down"));

    const html = await renderHomepage();

    expect(html).toContain("Acta · Publications");
    expect(html).not.toContain("Current events teaser");
    expect(html).not.toContain("See all");
  });

  it("returns null when no opinions are available", async () => {
    vi.mocked(listCurrents).mockResolvedValueOnce({ items: [] });

    const html = await renderHomepage();

    expect(html).toContain("Acta · Publications");
    expect(html).not.toContain("Current events teaser");
    expect(html).not.toContain("See all");
  });
});
