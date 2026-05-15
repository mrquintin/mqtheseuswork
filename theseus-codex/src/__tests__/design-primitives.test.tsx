import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  BadgeRow,
  Card,
  EmptyState,
  KbdHint,
  Panel,
  Pill,
  Toolbar,
} from "@/components/design";
import { APPROVED_CSS_VARS, tokens } from "@/lib/design/tokens";

/**
 * Snapshot + a11y/contrast spot-checks for the extracted design primitives.
 *
 * We don't reach for a full jsdom: every primitive is pure markup, so SSR
 * is enough to guard against accidental visual drift. The contrast tests
 * verify that focusable variants render with a visible border/glow.
 */

describe("design tokens", () => {
  it("exposes the palette, spacing, and type scales", () => {
    expect(tokens.color.amber).toBe("var(--amber)");
    expect(tokens.space.lg).toBe("1rem");
    expect(tokens.fontSize.body).toBe("0.9rem");
    expect(tokens.elevation.sm).toBe("var(--glow-sm)");
  });

  it("APPROVED_CSS_VARS includes every variable referenced by tokens.color", () => {
    for (const value of Object.values(tokens.color)) {
      const match = /var\((--[a-z0-9-]+)\)/i.exec(value);
      if (!match) continue;
      expect(APPROVED_CSS_VARS).toContain(match[1]);
    }
  });
});

describe("Pill", () => {
  it("renders the default outline variant", () => {
    const html = renderToStaticMarkup(<Pill>MQS 80%</Pill>);
    expect(html).toMatchInlineSnapshot(
      `"<span style="display:inline-flex;align-items:center;gap:0.25rem;padding:0.25rem 0.65rem;border:1px solid var(--border);border-radius:999px;background:transparent;color:var(--parchment-dim);font-family:&#x27;IBM Plex Mono&#x27;, monospace;font-size:0.65rem;letter-spacing:0.18em;text-transform:uppercase;text-decoration:none;line-height:1" data-tone="neutral" data-variant="outline">MQS 80%</span>"`,
    );
  });

  it("renders an anchor when href is provided", () => {
    const html = renderToStaticMarkup(
      <Pill href="/methodology#mqs" tone="accent">
        link
      </Pill>,
    );
    expect(html).toContain('<a href="/methodology#mqs"');
    expect(html).toContain('data-tone="accent"');
  });

  it("renders the filled variant with override colors", () => {
    const html = renderToStaticMarkup(
      <Pill
        variant="filled"
        size="sm"
        colors={{ fg: "#fff", bg: "#5b1414", border: "rgba(0,0,0,0.35)" }}
      >
        Retracted
      </Pill>,
    );
    expect(html).toContain("background:#5b1414");
    expect(html).toContain("color:#fff");
  });

  it("includes a visible 1px border for focus contrast at the default variant", () => {
    const html = renderToStaticMarkup(<Pill tone="accent">accent</Pill>);
    expect(html).toMatch(/border:1px solid var\(--amber-dim\)/);
  });
});

describe("Card", () => {
  it("renders the neutral card", () => {
    const html = renderToStaticMarkup(<Card>body</Card>);
    expect(html).toMatchInlineSnapshot(
      `"<div data-tone="neutral" style="background:var(--stone-light);border:1px solid var(--border);border-radius:6px;padding:1rem">body</div>"`,
    );
  });

  it("supports tone='accent' with an amber tint", () => {
    const html = renderToStaticMarkup(<Card tone="accent">accent body</Card>);
    expect(html).toContain('data-tone="accent"');
    expect(html).toContain("var(--amber)");
  });
});

describe("Panel", () => {
  it("renders a section with title, count, and meta", () => {
    const html = renderToStaticMarkup(
      <Panel title="Review queue" count={3} meta="sorted by urgency">
        <p>body</p>
      </Panel>,
    );
    expect(html).toContain("Review queue · 3");
    expect(html).toContain("sorted by urgency");
    expect(html).toMatch(/<section/);
  });

  it("renders a footer under a dashed divider when supplied", () => {
    const html = renderToStaticMarkup(
      <Panel title="x" footer={<span>tuning hint</span>}>
        body
      </Panel>,
    );
    expect(html).toContain("tuning hint");
    expect(html).toContain("dashed");
  });
});

describe("BadgeRow", () => {
  it("lays children out in a wrapping flex row", () => {
    const html = renderToStaticMarkup(
      <BadgeRow>
        <Pill>a</Pill>
        <Pill>b</Pill>
      </BadgeRow>,
    );
    expect(html).toMatch(/display:flex/);
    expect(html).toMatch(/flex-wrap:wrap/);
  });
});

describe("Toolbar", () => {
  it("renders leading and trailing zones around children", () => {
    const html = renderToStaticMarkup(
      <Toolbar leading={<span>L</span>} trailing={<span>R</span>}>
        <span>C</span>
      </Toolbar>,
    );
    expect(html).toContain('role="toolbar"');
    expect(html).toContain(">L<");
    expect(html).toContain(">C<");
    expect(html).toContain(">R<");
  });
});

describe("EmptyState", () => {
  it("renders kicker, title, and hint", () => {
    const html = renderToStaticMarkup(
      <EmptyState
        kicker="queue empty"
        title="No items need review."
        hint="New items appear within a minute of ingestion."
      />,
    );
    expect(html).toContain("queue empty");
    expect(html).toContain("No items need review.");
    expect(html).toContain('role="status"');
  });
});

describe("KbdHint", () => {
  it("renders a semantic <kbd> with a visible underline-style border", () => {
    const html = renderToStaticMarkup(<KbdHint>⌘K</KbdHint>);
    expect(html).toMatch(/^<kbd /);
    expect(html).toContain("⌘K");
    // 2px bottom border is the key affordance — kbd visually "sits" on the page
    expect(html).toContain("border-bottom-width:2px");
  });
});

describe("accessibility — focus rings", () => {
  it("Pill (as link) uses an underline-replacement focus affordance", () => {
    // Anchors render with text-decoration:none and rely on the border +
    // amber-dim outline. We assert the link has a non-zero border so a
    // focus ring isn't visually swallowed.
    const html = renderToStaticMarkup(<Pill href="/x">link</Pill>);
    expect(html).toMatch(/border:1px solid/);
  });

  it("EmptyState announces itself as role=status for SR users", () => {
    const html = renderToStaticMarkup(<EmptyState title="empty" />);
    expect(html).toContain('role="status"');
  });
});
