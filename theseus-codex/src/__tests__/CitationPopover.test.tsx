import type { ReactElement, ReactNode, RefObject } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PublicCitation } from "@/lib/currentsTypes";

type Listener = (event: {
  key?: string;
  preventDefault?: () => void;
  shiftKey?: boolean;
  target?: unknown;
}) => void;

interface Harness {
  cursor: number;
  cleanups: Array<(() => void) | undefined>;
  hooks: unknown[];
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
        harness.cleanups.push(effect() || undefined);
      },
      useId: () => {
        const index = harness.cursor++;
        if (!harness.hooks[index]) harness.hooks[index] = `r${index}`;
        return harness.hooks[index];
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
}

function mockPortal() {
  vi.doMock("react-dom", async () => {
    const actual = await vi.importActual<typeof import("react-dom")>("react-dom");
    return {
      ...actual,
      createPortal: (children: ReactNode) => children,
    };
  });
}

function fakeElement(name: string): HTMLElement {
  const element = {
    contains: (target: unknown) => target === element,
    focus: vi.fn(),
    getBoundingClientRect: () => ({
      bottom: 120,
      height: 20,
      left: 240,
      right: 300,
      top: 100,
      width: 60,
      x: 240,
      y: 100,
      toJSON: () => ({}),
    }),
    hasAttribute: () => false,
    offsetHeight: 220,
    querySelectorAll: () => [],
    tabIndex: 0,
    nodeName: name,
  };
  return element as unknown as HTMLElement;
}

function installDom() {
  const documentListeners = new Map<string, Listener[]>();
  const windowListeners = new Map<string, Listener[]>();
  const addListener = (map: Map<string, Listener[]>) => (type: string, listener: Listener) => {
    map.set(type, [...(map.get(type) ?? []), listener]);
  };
  const removeListener = (map: Map<string, Listener[]>) => (type: string, listener: Listener) => {
    map.set(
      type,
      (map.get(type) ?? []).filter((item) => item !== listener),
    );
  };

  vi.stubGlobal("document", {
    activeElement: null,
    addEventListener: addListener(documentListeners),
    body: fakeElement("body"),
    documentElement: { clientHeight: 768, clientWidth: 1024 },
    removeEventListener: removeListener(documentListeners),
  });
  vi.stubGlobal("window", {
    addEventListener: addListener(windowListeners),
    cancelAnimationFrame: vi.fn(),
    innerHeight: 768,
    innerWidth: 1024,
    removeEventListener: removeListener(windowListeners),
    requestAnimationFrame: (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    },
  });

  return { documentListeners, windowListeners };
}

type TestCitation = PublicCitation & {
  conclusion_title?: string | null;
  source_visibility?: string | null;
};

function citation(overrides: Partial<TestCitation> = {}): TestCitation {
  return {
    id: "citation-1",
    source_kind: "conclusion",
    source_id: "source-1",
    quoted_span: "quoted span",
    retrieval_score: 0.91,
    is_revoked: false,
    conclusion_title: "Source conclusion",
    source_visibility: "org",
    ...overrides,
  };
}

async function setup(
  overrides: {
    citation?: ReturnType<typeof citation>;
    conclusionText?: string;
    publicUrl?: string | null;
  } = {},
) {
  vi.resetModules();
  const harness: Harness = { cleanups: [], cursor: 0, hooks: [] };
  mockReact(harness);
  mockPortal();
  const { documentListeners } = installDom();
  const { default: CitationPopover } = await import("@/components/CitationPopover");
  const anchorRef = {
    current: fakeElement("anchor"),
  } as unknown as RefObject<HTMLElement | null>;
  const onClose = vi.fn();
  const render = () => {
    harness.cursor = 0;
    return CitationPopover({
      anchorRef,
      citation: overrides.citation ?? citation(),
      conclusionText:
        overrides.conclusionText ??
        "Materially improves **decision** quality.",
      onClose,
      open: true,
      publicUrl:
        "publicUrl" in overrides
          ? (overrides.publicUrl ?? null)
          : "/c/public-conclusion/v/1",
    }) as ReactElement;
  };

  return { documentListeners, onClose, render };
}

describe("CitationPopover", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.doUnmock("react");
    vi.doUnmock("react-dom");
    vi.resetModules();
  });

  it("renders the kind caption and sanitized conclusion text", async () => {
    const { render } = await setup();

    const html = renderToStaticMarkup(render());

    expect(html).toContain("firm conclusion");
    expect(html).toContain("Source conclusion");
    expect(html).toContain("Materially improves ");
    expect(html).toContain("<strong>decision</strong>");
  });

  it("renders the public-source link only when publicUrl is present and visibility is org", async () => {
    const { render } = await setup();

    const html = renderToStaticMarkup(render());

    expect(html).toContain('href="/c/public-conclusion/v/1"');
    expect(html).toContain("Open the public conclusion");
  });

  it("hides the link when publicUrl is null", async () => {
    const { render } = await setup({ publicUrl: null });

    const html = renderToStaticMarkup(render());

    expect(html).not.toContain("Open the public conclusion");
    expect(html).toContain("Source recorded by the firm; not publicly available.");
  });

  it("hides the link when visibility is private", async () => {
    const { render } = await setup({
      citation: citation({ source_visibility: "private" }),
      publicUrl: "/c/private-conclusion/v/1",
    });

    const html = renderToStaticMarkup(render());

    expect(html).not.toContain('href="/c/private-conclusion/v/1"');
    expect(html).toContain("Source recorded by the firm; not publicly available.");
  });

  it("ESC and outside-click close the popover", async () => {
    const { documentListeners, onClose, render } = await setup();
    render();

    documentListeners.get("keydown")?.[0]?.({
      key: "Escape",
      preventDefault: vi.fn(),
    });
    documentListeners.get("mousedown")?.[0]?.({
      target: fakeElement("outside"),
    });

    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
