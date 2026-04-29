import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

type ButtonElement = ReactElement<{
  children: ReactNode;
  onClick: () => Promise<void>;
}>;

async function loadButtonHarness(opinionId = "opinion-abc") {
  let copied = false;
  const setCopied = vi.fn((next: boolean | ((current: boolean) => boolean)) => {
    copied = typeof next === "function" ? next(copied) : next;
  });

  vi.doMock("react", async () => {
    const actual = await vi.importActual<typeof import("react")>("react");

    return {
      ...actual,
      useState: () => [copied, setCopied],
    };
  });

  const { CopyLinkButton } = await import(
    "@/app/currents/[id]/CopyLinkButton"
  );

  return {
    render: () => CopyLinkButton({ opinionId }) as ButtonElement,
    setCopied,
  };
}

describe("CopyLinkButton", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.doUnmock("react");
    vi.resetModules();
  });

  it("copies the exact permalink without UTM params or share instrumentation", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    vi.stubGlobal("window", {
      location: { origin: "https://theseuscodex.com" },
      prompt: vi.fn(),
    });

    const { render } = await loadButtonHarness("opinion-abc");

    expect(render().props.children).toBe("copy permalink");

    await render().props.onClick();

    expect(writeText).toHaveBeenCalledWith(
      "https://theseuscodex.com/currents/opinion-abc",
    );
    expect(writeText.mock.calls[0][0]).not.toContain("?");
    expect(render().props.children).toBe("permalink copied");

    vi.advanceTimersByTime(1399);
    expect(render().props.children).toBe("permalink copied");

    vi.advanceTimersByTime(1);
    expect(render().props.children).toBe("copy permalink");
  });
});
