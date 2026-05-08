import React, { type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import OpinionCard from "@/app/currents/OpinionCard";
import XPostEmbed from "@/app/currents/XPostEmbed";
import type { PublicCitation, PublicOpinion } from "@/lib/currentsTypes";

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

type TestCitation = PublicCitation & {
  conclusion_text?: string | null;
  conclusion_title?: string | null;
  public_url?: string | null;
  source_visibility?: string | null;
};

function citation(
  index: number,
  sourceKind = "claim",
  overrides: Partial<TestCitation> = {},
): TestCitation {
  return {
    id: `citation-${index}`,
    source_kind: sourceKind,
    source_id: `source-${index}`,
    quoted_span: `quoted span ${index}`,
    retrieval_score: 0.91,
    is_revoked: false,
    conclusion_text: `Conclusion text ${index}`,
    conclusion_title: `Conclusion ${index}`,
    public_url: null,
    source_visibility: null,
    ...overrides,
  };
}

function opinion(overrides: Partial<PublicOpinion> = {}): PublicOpinion {
  return {
    id: "opinion-1",
    organization_id: "org-1",
    event_id: "event-1",
    stance: "complicates",
    confidence: 0.72,
    headline: "Markets misread the signal",
    body_markdown: "This is **supported** but *qualified* with `code`.",
    uncertainty_notes: [],
    topic_hint: "markets",
    model_name: "test-model",
    generated_at: "2026-04-29T12:00:00.000Z",
    revoked_at: null,
    abstention_reason: null,
    revoked_sources_count: 0,
    event: {
      id: "event-1",
      source: "X_TWITTER",
      external_id: "external-1",
      author_handle: "analyst",
      text: "The mayor announced a new transit funding plan on X.",
      url: "https://x.com/analyst/status/external-1",
      captured_at: "2026-04-29T12:00:00.000Z",
      observed_at: "2026-04-29T11:59:00.000Z",
      topic_hint: "macro",
    },
    citations: [citation(1, "conclusion"), citation(2, "claim")],
    ...overrides,
  };
}

describe("OpinionCard", () => {
  it("renders the stance pill, headline, and safe markdown body", () => {
    const html = renderToStaticMarkup(
      <OpinionCard
        opinion={opinion({
          body_markdown:
            "This is **supported** but *qualified* with `code` and [evidence](https://example.com/source).",
        })}
      />,
    );

    expect(html).toContain("complicates");
    expect(html).toContain("Markets misread the signal");
    expect(html).toContain("<strong>supported</strong>");
    expect(html).toContain("<em>qualified</em>");
    expect(html).toContain("<code");
    expect(html).toContain(">code</code>");
    expect(html).toContain('rel="noopener nofollow ugc"');
    expect(html).toContain('target="_blank"');
  });

  it("renders the observed X post as the object being analyzed", () => {
    const html = renderToStaticMarkup(<OpinionCard opinion={opinion()} />);

    expect(html).toContain("twitter-tweet");
    expect(html).toContain('data-theme="dark"');
    expect(html).toContain('data-theseus-x-embed="card"');
    expect(html).toContain("background:var(--currents-bg-elevated)");
    expect(html).toContain("border-radius:16px");
    expect(html).toContain("overflow:hidden");
    expect(html).toContain("https://twitter.com/analyst/status/external-1");
    expect(html).toContain("@analyst");
    expect(html).toContain("The mayor announced a new transit funding plan on X.");
    expect(html).toContain("X post");
    expect(html).not.toContain("source X post");
  });

  it("paints standalone X embeds against the Currents page surface", () => {
    const html = renderToStaticMarkup(
      <XPostEmbed
        fallbackText="Standalone post copy."
        surface="page"
        url="https://x.com/analyst/status/external-2"
      />,
    );

    expect(html).toContain("twitter-tweet");
    expect(html).toContain('data-theseus-x-embed="page"');
    expect(html).toContain("background:var(--currents-bg)");
    expect(html).toContain("https://twitter.com/analyst/status/external-2");
  });

  it("renders inline citation buttons and removes the rationale strip", () => {
    const html = renderToStaticMarkup(
      <OpinionCard
        opinion={opinion({
          body_markdown:
            "The firm leans on one conclusion [1] and one opinion [2].",
          citations: [
            citation(1, "conclusion"),
            citation(2, "claim"),
            citation(3, "claim"),
            citation(4, "claim"),
            citation(5, "claim"),
          ],
        })}
      />,
    );

    expect(html).not.toContain("Firm rationale links");
    expect(html).not.toContain("/currents/opinion-1#src-source-1");
    expect(html).toContain("[firm conclusion]");
    expect(html).toContain("[opinion]");
    expect(html).toContain('aria-haspopup="dialog"');
  });

  it("renders firm conclusion tokens from current [C:id] markers", () => {
    const html = renderToStaticMarkup(
      <OpinionCard
        opinion={opinion({
          body_markdown:
            "The firm treats this as a live test of judgment [C:source-1].",
          citations: [citation(1, "conclusion")],
        })}
      />,
    );

    expect(html).not.toContain("[C:source-1]");
    expect(html).toContain("[firm conclusion]");
    expect(html).toContain('aria-haspopup="dialog"');
  });

  it("escapes markdown containing script tags", () => {
    const html = renderToStaticMarkup(
      <OpinionCard
        opinion={opinion({
          body_markdown: 'Claim <script>alert("x")</script> stays inert.',
        })}
      />,
    );

    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("&lt;/script&gt;");
  });

  it("links the follow-up CTA to the opinion ask anchor", () => {
    const html = renderToStaticMarkup(<OpinionCard opinion={opinion()} />);

    expect(html).toContain('href="/currents/opinion-1#ask"');
    expect(html).toContain("Ask a follow-up");
  });

  it("opens a citation popover when an inline opinion token is clicked", async () => {
    vi.resetModules();
    const harness: { cursor: number; hooks: unknown[] } = { cursor: 0, hooks: [] };
    vi.doMock("react", async () => {
      const actual = await vi.importActual<typeof import("react")>("react");
      return {
        ...actual,
        useCallback: <T extends (...args: never[]) => unknown>(callback: T) => {
          harness.cursor += 1;
          return callback;
        },
        useId: () => {
          const index = harness.cursor++;
          if (!harness.hooks[index]) harness.hooks[index] = `r${index}`;
          return harness.hooks[index];
        },
        useMemo: <T,>(factory: () => T) => {
          harness.cursor += 1;
          return factory();
        },
        useRef: <T,>(initial: T) => {
          const index = harness.cursor++;
          if (!harness.hooks[index]) harness.hooks[index] = { current: initial };
          return harness.hooks[index];
        },
        useState: <T,>(initial: T | (() => T)) => {
          const index = harness.cursor++;
          if (!(index in harness.hooks)) {
            harness.hooks[index] =
              typeof initial === "function" ? (initial as () => T)() : initial;
          }
          const setState = (next: T | ((previous: T) => T)) => {
            const previous = harness.hooks[index] as T;
            harness.hooks[index] =
              typeof next === "function"
                ? (next as (previous: T) => T)(previous)
                : next;
          };
          return [harness.hooks[index] as T, setState] as const;
        },
      };
    });
    vi.doMock("@/components/CitationPopover", () => ({
      default: ({
        conclusionText,
        open,
      }: {
        conclusionText: string;
        open: boolean;
      }) => (open ? <aside role="dialog">{conclusionText}</aside> : null),
    }));

    const { OpinionMarkdownBody } = await import("@/app/currents/OpinionCard");
    const render = () => {
      harness.cursor = 0;
      return OpinionMarkdownBody({
        opinion: opinion({
          body_markdown: "This marker opens [1].",
          citations: [
            citation(1, "claim", {
              conclusion_text: "The firm stores this claim conclusion.",
            }),
          ],
        }),
      }) as ReactElement;
    };

    let tree = render();
    const button = findAllByType(tree, "button").find(
      (element) => textContent(element) === "[opinion]",
    );
    expect(button).toBeTruthy();

    button?.props.onClick({ currentTarget: {} });
    tree = render();

    expect(renderToStaticMarkup(tree)).toContain(
      "The firm stores this claim conclusion.",
    );

    vi.doUnmock("react");
    vi.doUnmock("@/components/CitationPopover");
    vi.resetModules();
  });
});

function childrenOf(node: ReactNode): ReactNode[] {
  if (!node || typeof node !== "object") return [];
  const children = (node as ReactElement<{ children?: ReactNode }>).props?.children;
  return Array.isArray(children) ? children : children === undefined ? [] : [children];
}

function walk(node: ReactNode, visitor: (element: ReactElement) => void): void {
  if (!node || typeof node !== "object") return;
  if (Array.isArray(node)) {
    node.forEach((child) => walk(child, visitor));
    return;
  }
  const element = node as ReactElement;
  visitor(element);
  childrenOf(element).forEach((child) => walk(child, visitor));
}

function findAllByType(tree: ReactNode, type: string): ReactElement[] {
  const found: ReactElement[] = [];
  walk(tree, (element) => {
    if (element.type === type) found.push(element);
  });
  return found;
}

function textContent(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textContent).join("");
  if (typeof node === "object") return childrenOf(node).map(textContent).join("");
  return "";
}
