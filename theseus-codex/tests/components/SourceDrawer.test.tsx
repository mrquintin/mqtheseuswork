import type { ReactElement, ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PublicForecastSource } from "@/lib/forecastsTypes";

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

interface Harness {
  cursor: number;
  hooks: unknown[];
}

function source(index: number, overrides: Partial<PublicForecastSource> = {}): PublicForecastSource {
  return {
    id: `citation-${index}`,
    prediction_id: "prediction-1",
    source_type: "CONCLUSION",
    source_id: `source-${index}`,
    source_text: `Before ${index}. This is the exact quoted span ${index} in context. After ${index}.`,
    quoted_span: `exact quoted span ${index}`,
    support_label: "DIRECT",
    retrieval_score: 0.8 + index / 100,
    is_revoked: false,
    revoked_reason: null,
    canonical_path: `/c/source-${index}`,
    ...overrides,
  };
}

function mockReact(harness: Harness) {
  vi.doMock("react", async () => {
    const actual = await vi.importActual<typeof import("react")>("react");
    return {
      ...actual,
      useCallback: <T extends (...args: never[]) => unknown>(callback: T) => {
        harness.cursor += 1;
        return callback;
      },
      useEffect: (effect: () => void | (() => void)) => {
        harness.cursor += 1;
        return effect();
      },
      useMemo: <T,>(factory: () => T) => {
        harness.cursor += 1;
        return factory();
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
}

describe("Forecast SourceDrawer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.doUnmock("react");
    vi.resetModules();
  });

  it("renders with 3 citations; cycling ] 4 times wraps to the first citation", async () => {
    const harness: Harness = { cursor: 0, hooks: [] };
    let keydown: ((event: KeyboardEvent) => void) | null = null;

    mockReact(harness);
    vi.stubGlobal("window", {
      addEventListener: (type: string, listener: (event: KeyboardEvent) => void) => {
        if (type === "keydown") keydown = listener;
      },
      removeEventListener: vi.fn(),
      setTimeout: (callback: () => void) => callback(),
    });
    vi.stubGlobal("document", {
      getElementById: () => null,
    });

    const { default: SourceDrawer } = await import("@/app/forecasts/[id]/SourceDrawer");
    const sources = [source(1), source(2), source(3)];
    const render = () => {
      harness.cursor = 0;
      return SourceDrawer({ sources }) as ReactElement;
    };

    expect(renderToStaticMarkup(render())).toContain("CONCLUSION/source-3");

    for (let count = 0; count < 4; count += 1) {
      keydown?.({ key: "]", preventDefault: vi.fn(), target: null } as unknown as KeyboardEvent);
    }

    const html = renderToStaticMarkup(render());
    expect(html).toContain('data-active="true"');
    expect(html).toMatch(/data-active="true"[\s\S]*CONCLUSION\/source-1/);
  });

  it("highlights the exact verbatim span with a mark element", async () => {
    const { default: SourceDrawer } = await import("@/app/forecasts/[id]/SourceDrawer");
    const html = renderToStaticMarkup(
      <SourceDrawer activeSourceId="source-1" sources={[source(1)]} />,
    );

    expect(html).toContain("<mark");
    expect(html).toContain(">exact quoted span 1</mark>");
  });

  it("renders a red verification failure box when the quoted span is absent", async () => {
    const { default: SourceDrawer } = await import("@/app/forecasts/[id]/SourceDrawer");
    const html = renderToStaticMarkup(
      <SourceDrawer
        activeSourceId="source-1"
        sources={[source(1, { quoted_span: "fabricated quote" })]}
      />,
    );

    expect(html).toContain("CITATION FAILED VERIFICATION");
    expect(html).toContain("fabricated quote");
  });

  it("Esc closes the drawer", async () => {
    const harness: Harness = { cursor: 0, hooks: [] };
    let keydown: ((event: KeyboardEvent) => void) | null = null;

    mockReact(harness);
    vi.stubGlobal("window", {
      addEventListener: (type: string, listener: (event: KeyboardEvent) => void) => {
        if (type === "keydown") keydown = listener;
      },
      removeEventListener: vi.fn(),
      setTimeout: (callback: () => void) => callback(),
    });

    const { default: SourceDrawer } = await import("@/app/forecasts/[id]/SourceDrawer");
    const render = () => {
      harness.cursor = 0;
      return SourceDrawer({ sources: [source(1), source(2), source(3)] }) as ReactElement;
    };

    expect(renderToStaticMarkup(render())).toContain("Citation drawer");
    keydown?.({ key: "Escape", target: null } as unknown as KeyboardEvent);

    const html = renderToStaticMarkup(render());
    expect(html).toContain("Open citations");
    expect(html).not.toContain("CONCLUSION/source-1");
  });
});
