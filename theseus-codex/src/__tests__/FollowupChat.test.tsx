import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PublicSource } from "@/lib/currentsTypes";

const fetchMock = vi.fn();

class MemoryStorage implements Storage {
  private values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.values.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

interface Harness {
  cursor: number;
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
      useEffect: () => {
        harness.cursor += 1;
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
}

function source(overrides: Partial<PublicSource> = {}): PublicSource {
  return {
    id: "citation-1",
    opinion_id: "opinion-1",
    source_kind: "conclusion",
    source_id: "source1",
    source_text: "Source text",
    quoted_span: "Source",
    retrieval_score: 0.9,
    is_revoked: false,
    revoked_reason: null,
    canonical_path: "/c/source1",
    ...overrides,
  };
}

function frame(kind: string, payload: unknown): string {
  return `event: ${kind}\ndata: ${JSON.stringify({ kind, payload })}\n\n`;
}

function sseResponse(...frames: string[]): Response {
  return new Response(frames.join(""), {
    status: 200,
    headers: { "content-type": "text/event-stream; charset=utf-8" },
  });
}

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

function findByType(tree: ReactNode, type: string): ReactElement {
  let found: ReactElement | null = null;
  walk(tree, (element) => {
    if (!found && element.type === type) found = element;
  });
  if (!found) throw new Error(`No <${type}> found`);
  return found;
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

async function flushAsyncWork(): Promise<void> {
  for (let index = 0; index < 10; index += 1) {
    await Promise.resolve();
  }
}

async function setup(sources: PublicSource[] = [source()]) {
  const harness: Harness = { cursor: 0, hooks: [] };
  mockReact(harness);
  const { default: FollowupChat } = await import("@/app/currents/[id]/FollowupChat");

  const render = () => {
    harness.cursor = 0;
    return FollowupChat({ opinionId: "opinion-1", sources });
  };

  return { render };
}

async function askQuestion(render: () => ReactElement, question = "What follows?") {
  let tree = render();
  const textarea = findByType(tree, "textarea");
  textarea.props.onChange({ target: { value: question } });
  tree = render();
  const button = findByType(tree, "button");
  button.props.onClick?.({});
  button.props.onSubmit?.({});
  const form = findByType(tree, "form");
  form.props.onSubmit({ preventDefault: () => undefined });
  await flushAsyncWork();
  return render();
}

describe("FollowupChat", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-29T12:00:00.000Z"));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("sessionStorage", new MemoryStorage());
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.doUnmock("react");
    vi.resetModules();
  });

  it("clicking send POSTs to the correct URL", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse(frame("done", {})));
    const { render } = await setup();

    await askQuestion(render);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/currents/opinion-1/follow-up");
    expect(init).toMatchObject({
      method: "POST",
      cache: "no-store",
    });
    expect(JSON.parse(String(init.body))).toEqual({ question: "What follows?" });
  });

  it("saves the streamed meta session id to sessionStorage", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(
        frame("meta", { session_id: "session-123" }),
        frame("done", {}),
      ),
    );
    const storage = globalThis.sessionStorage;
    const { render } = await setup();

    await askQuestion(render);

    expect(storage.getItem("currents.followup.opinion-1")).toContain('"session_id":"session-123"');
  });

  it("accumulates SSE token events in the assistant message bubble", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(
        frame("token", { text: "Hello" }),
        frame("token", { text: " world" }),
        frame("done", {}),
      ),
    );
    const { render } = await setup();

    const tree = await askQuestion(render);

    expect(textContent(tree)).toContain("Hello world");
  });

  it("keeps the send button disabled during the 2s client interval", async () => {
    fetchMock.mockResolvedValueOnce(sseResponse(frame("done", {})));
    const { render } = await setup();

    let tree = await askQuestion(render);
    const textarea = findByType(tree, "textarea");
    textarea.props.onChange({ target: { value: "Second question?" } });
    tree = render();

    expect(findByType(tree, "button").props.disabled).toBe(true);
  });

  it("does not render a citation whose source_id is outside the known retrieval set", async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(
        frame("token", { text: "Answer." }),
        frame("citation", { source_kind: "claim", source_id: "hallucinated" }),
        frame("done", {}),
      ),
    );
    const { render } = await setup([source({ source_id: "source1" })]);

    const tree = await askQuestion(render);
    const hrefs = findAllByType(tree, "a").map((anchor) => anchor.props.href);

    expect(hrefs).not.toContain("/c/hallucinated#claim-hallucinated");
    expect(textContent(tree)).not.toContain("⸺ claim");
  });
});
