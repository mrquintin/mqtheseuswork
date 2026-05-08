import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { PublishedConclusion } from "@/lib/conclusionsRead";

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

import ConclusionView from "@/components/ConclusionView";

function conclusion(overrides: Partial<PublishedConclusion> = {}): PublishedConclusion {
  return {
    id: "article-1",
    kind: "ARTICLE",
    slug: "mixed-case-public-title",
    version: 1,
    sourceConclusionId: "conclusion-1",
    publishedAt: "2026-05-01T12:00:00.000Z",
    doi: "10.1234/theseus.article",
    zenodoRecordId: "zenodo-1",
    discountedConfidence: 0.81,
    statedConfidence: 0.86,
    calibrationDiscountReason: "test fixture",
    payload: {
      schema: "theseus.publicConclusion.v1",
      conclusionText: "Mixed Case Public Title, Not Yelling",
      rationale: "Rationale that should remain available to the loader.",
      topicHint: "typography",
      evidenceSummary: "Evidence summary that should remain available to the loader.",
      exitConditions: ["CLUTTER_EXIT_CONDITION"],
      strongestObjection: {
        objection: "CLUTTER_STRONGEST_OBJECTION",
        firmAnswer: "CLUTTER_FIRM_ANSWER",
      },
      openQuestionsAdjacent: [],
      voiceComparisons: [],
      methodology: {
        schema: "theseus.methodology.v1",
        reviewerNarrative: "",
        profiles: [],
      },
      timeline: [
        {
          at: "2026-05-01T12:00:00.000Z",
          label: "CLUTTER_EVOLUTION_EVENT",
        },
      ],
      whatWouldChangeOurMind: ["CLUTTER_CHANGE_OUR_MIND"],
      citations: [{ format: "apa", block: "CLUTTER_CITATION_BLOCK" }],
      article: {
        kind: "THEMATIC",
        bodyMarkdown:
          "## Mixed Case Article Subheading\n\nThe firm body copy should be eligible for browser justification and hyphenation without server-side title uppercasing.",
        sourceIds: [],
        citations: [],
      },
    },
    ...overrides,
  };
}

describe("ConclusionView", () => {
  it("preserves the public title text, justifies article prose, and omits clutter sections", () => {
    const row = conclusion();
    const html = renderToStaticMarkup(
      <ConclusionView row={row} allVersions={[row]} responses={[]} />,
    );
    const h1 = html.match(/<h1 class="public-title">([^<]*)<\/h1>/);

    expect(h1?.[1]).toBe(row.payload.conclusionText);
    expect(html).toContain('class="public-article-body"');
    expect(html).toContain("Mixed Case Article Subheading");
    expect(html).not.toContain("text-transform:uppercase");
    expect(html).not.toContain("Strongest engaged objection");
    expect(html).not.toContain("CLUTTER_STRONGEST_OBJECTION");
    expect(html).not.toContain("What would change our mind");
    expect(html).not.toContain("CLUTTER_CHANGE_OUR_MIND");
    expect(html).not.toContain("Evolution (time machine)");
    expect(html).not.toContain("CLUTTER_EVOLUTION_EVENT");
    expect(html).not.toContain("<h2>Citations</h2>");
    expect(html).not.toContain("CLUTTER_CITATION_BLOCK");
  });

  it("keeps public-title out of CSS uppercasing", () => {
    const cssPath = fileURLToPath(new URL("../app/globals.css", import.meta.url));
    const css = readFileSync(cssPath, "utf8");
    const publicTitleBlock = css.match(/\.public-title\s*\{(?<body>[^}]*)\}/)?.groups?.body;
    const publicArticleBodyBlock = css.match(/\.public-article-body\s*\{(?<body>[^}]*)\}/)?.groups?.body;

    expect(publicTitleBlock).toContain("font-family: 'EB Garamond', 'Iowan Old Style', Georgia, serif;");
    expect(publicTitleBlock).not.toMatch(/text-transform\s*:\s*uppercase/i);
    expect(publicArticleBodyBlock).toContain("text-align: justify;");
    expect(publicArticleBodyBlock).toContain("hyphens: auto;");
  });
});
