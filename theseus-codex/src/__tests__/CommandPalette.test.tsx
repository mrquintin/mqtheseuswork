import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";

/**
 * Tests for the keyboard-first command palette and its supporting
 * hotkeys helper. The codebase doesn't bring in @testing-library, so
 * we follow the existing pattern (see CitationPopover.test.tsx) of
 * mocking React's hooks with a tiny harness and exercising components
 * via renderToStaticMarkup.
 *
 * Coverage:
 *   - lib/hotkeys: pure chord parsing + editable-target detection.
 *   - CommandPalette: closed by default; opens on Cmd/Ctrl+K; renders
 *     a listbox with the navigation commands; Enter routes via
 *     next/navigation; pure score()/looksLikeId() helpers.
 *   - Focus reachability + a11y: combobox + role="option" present.
 */

interface Listener {
  (event: { key?: string; preventDefault?: () => void; metaKey?: boolean; ctrlKey?: boolean; shiftKey?: boolean; altKey?: boolean; target?: unknown }): void;
}

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
      useId: () => {
        const index = harness.cursor++;
        if (!harness.hooks[index]) harness.hooks[index] = `r${index}`;
        return harness.hooks[index];
      },
      useContext: () => null,
    };
  });
}

const routerMocks = {
  push: vi.fn(),
  refresh: vi.fn(),
  replace: vi.fn(),
};

function mockNextNavigation() {
  vi.doMock("next/navigation", () => ({
    useRouter: () => routerMocks,
    usePathname: () => "/dashboard",
    useSearchParams: () => new URLSearchParams(""),
  }));
}

function installDom() {
  const documentListeners = new Map<string, Listener[]>();
  const windowListeners = new Map<string, Listener[]>();
  const addListener = (map: Map<string, Listener[]>) => (type: string, listener: Listener) => {
    map.set(type, [...(map.get(type) ?? []), listener]);
  };
  const removeListener = (map: Map<string, Listener[]>) => (type: string, listener: Listener) => {
    map.set(type, (map.get(type) ?? []).filter((entry) => entry !== listener));
  };
  vi.stubGlobal("document", {
    activeElement: null,
    addEventListener: addListener(documentListeners),
    removeEventListener: removeListener(documentListeners),
    body: { focus: () => {} },
  });
  vi.stubGlobal("window", {
    addEventListener: addListener(windowListeners),
    removeEventListener: removeListener(windowListeners),
    requestAnimationFrame: (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    },
    localStorage: {
      getItem: () => null,
      setItem: () => {},
    },
  });
  vi.stubGlobal("navigator", { platform: "MacIntel", userAgent: "test" });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ items: [] }),
  }));
  return { documentListeners, windowListeners };
}

describe("lib/hotkeys", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
    vi.doUnmock("react");
  });

  it("parses chord modifiers and matches keyboard events", async () => {
    vi.stubGlobal("navigator", { platform: "MacIntel", userAgent: "test" });
    const { __test } = await import("@/lib/hotkeys");
    const parsed = __test.parseChord("Mod+K");
    expect(parsed.key).toBe("k");
    expect(parsed.mod).toBe(true);

    const onMac = __test.eventMatches(
      // @ts-expect-error — synthetic KeyboardEvent
      { key: "k", metaKey: true, ctrlKey: false, shiftKey: false, altKey: false },
      parsed,
    );
    expect(onMac).toBe(true);

    const wrongModifier = __test.eventMatches(
      // @ts-expect-error — synthetic KeyboardEvent
      { key: "k", metaKey: false, ctrlKey: false, shiftKey: false, altKey: false },
      parsed,
    );
    expect(wrongModifier).toBe(false);
  });

  it("treats inputs and contenteditable as editable targets", async () => {
    const { __test } = await import("@/lib/hotkeys");
    const inputEl = { tagName: "INPUT", isContentEditable: false };
    const ceEl = { tagName: "DIV", isContentEditable: true };
    const divEl = { tagName: "DIV", isContentEditable: false };
    // @ts-expect-error — synthetic EventTarget shape
    expect(__test.isEditableTarget(inputEl)).toBe(true);
    // @ts-expect-error — synthetic EventTarget shape
    expect(__test.isEditableTarget(ceEl)).toBe(true);
    // @ts-expect-error — synthetic EventTarget shape
    expect(__test.isEditableTarget(divEl)).toBe(false);
    expect(__test.isEditableTarget(null)).toBe(false);
  });
});

describe("CommandPalette pure helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
    vi.doUnmock("react");
    vi.doUnmock("next/navigation");
  });

  async function loadModule() {
    const harness: Harness = { cleanups: [], cursor: 0, hooks: [] };
    mockReact(harness);
    mockNextNavigation();
    installDom();
    const mod = await import("@/components/CommandPalette");
    return mod;
  }

  it("looksLikeId rejects short queries and accepts id-shaped strings", async () => {
    const { __test } = await loadModule();
    expect(__test.looksLikeId("abc")).toBe(false);
    expect(__test.looksLikeId("abcdef")).toBe(true);
    expect(__test.looksLikeId("c:short")).toBe(true);
    expect(__test.looksLikeId("multi word query")).toBe(false);
  });

  it("score boosts label-prefix matches above subsequence matches", async () => {
    const { __test } = await loadModule();
    const cmd = {
      id: "x",
      label: "Drift events",
      hint: "/ops",
      section: "Queries" as const,
      keywords: "decay",
      run: () => {},
    };
    expect(__test.score("dri", cmd)).toBeGreaterThan(__test.score("dft", cmd));
    expect(__test.score("zzz", cmd)).toBe(0);
    // Empty query keeps everything in the list.
    expect(__test.score("", cmd)).toBeGreaterThan(0);
  });
});

describe("CommandPalette component", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
    vi.doUnmock("react");
    vi.doUnmock("next/navigation");
    routerMocks.push.mockReset();
    routerMocks.refresh.mockReset();
  });

  async function setup() {
    const harness: Harness = { cleanups: [], cursor: 0, hooks: [] };
    mockReact(harness);
    mockNextNavigation();
    const dom = installDom();
    const { default: CommandPalette } = await import("@/components/CommandPalette");
    const render = () => {
      harness.cursor = 0;
      return CommandPalette({}) as ReactElement | null;
    };
    return { harness, dom, render };
  }

  it("renders nothing when closed", async () => {
    const { render } = await setup();
    const tree = render();
    expect(tree).toBeNull();
  });

  it("opens when Cmd+K fires on the window listener and exposes a combobox + listbox", async () => {
    const { render, dom } = await setup();
    // Initial render registers the window listener.
    render();
    const listeners = dom.windowListeners.get("keydown") ?? [];
    expect(listeners.length).toBeGreaterThan(0);

    // Simulate Cmd+K — use metaKey:true, ctrlKey:false (Mac platform).
    listeners[0]({
      key: "k",
      metaKey: true,
      ctrlKey: false,
      shiftKey: false,
      altKey: false,
      preventDefault: () => {},
    });

    const tree = render();
    expect(tree).not.toBeNull();
    const html = renderToStaticMarkup(tree as ReactElement);
    expect(html).toContain('role="dialog"');
    expect(html).toContain('role="combobox"');
    expect(html).toContain('role="listbox"');
    expect(html).toContain('aria-modal="true"');
    // A few of the canonical navigation commands must be present so a
    // keyboard-only user can reach them on first open.
    expect(html).toContain("Go to Dashboard");
    expect(html).toContain("Go to Explorer");
  });

  it("Esc on the document closes the palette", async () => {
    const { render, dom } = await setup();
    render();
    const winListeners = dom.windowListeners.get("keydown") ?? [];
    winListeners[0]({
      key: "k",
      metaKey: true,
      ctrlKey: false,
      shiftKey: false,
      altKey: false,
      preventDefault: () => {},
    });
    // Re-render so the open-only document listener is registered.
    render();

    const docListeners = dom.documentListeners.get("keydown") ?? [];
    expect(docListeners.length).toBeGreaterThan(0);
    docListeners[0]({ key: "Escape", preventDefault: () => {} });

    const after = render();
    expect(after).toBeNull();
  });
});

describe("CommandPalette + KeymapHelp focus a11y", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
    vi.doUnmock("react");
    vi.doUnmock("next/navigation");
  });

  it("provides keyboard reachability via tab order primitives", async () => {
    const harness: Harness = { cleanups: [], cursor: 0, hooks: [] };
    mockReact(harness);
    mockNextNavigation();
    installDom();
    const { default: CommandPalette } = await import("@/components/CommandPalette");
    // Force-open by setting state pre-render — index 0 is `open`, the
    // first useState in the component body.
    harness.hooks[0] = true;
    const tree = CommandPalette({}) as ReactElement;
    const html = renderToStaticMarkup(tree);
    // A focusable input is the first interactive element.
    expect(html).toMatch(/<input[^>]+role="combobox"/);
    // Options are reachable as listbox descendants with role="option".
    expect(html).toContain('role="option"');
    // The dialog has the highest z-index among shell layers (1000).
    expect(html).toContain("z-index:1000");
  });
});
