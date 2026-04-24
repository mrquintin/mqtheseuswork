// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render } from "@testing-library/react";

import { CopyLinkButton } from "@/app/currents/[id]/CopyLinkButton";

const writeText = vi.fn<(s: string) => Promise<void>>().mockResolvedValue(undefined);

beforeEach(() => {
  writeText.mockReset();
  writeText.mockResolvedValue(undefined);
  vi.stubGlobal("navigator", {
    clipboard: { writeText },
  });
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("CopyLinkButton", () => {
  it("writes the permalink to the clipboard and flips label to 'permalink copied'", async () => {
    const { getByRole } = render(<CopyLinkButton opinionId="op-xyz" />);
    const button = getByRole("button");
    expect(button.textContent).toBe("copy permalink");

    await act(async () => {
      fireEvent.click(button);
      // Let the awaited clipboard write resolve.
      await Promise.resolve();
    });

    expect(writeText).toHaveBeenCalledTimes(1);
    const origin = window.location.origin;
    expect(writeText).toHaveBeenCalledWith(`${origin}/currents/op-xyz`);
    expect(button.textContent).toBe("permalink copied");

    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    expect(button.textContent).toBe("copy permalink");
  });

  it("URL-encodes the opinion id when building the permalink", async () => {
    const { getByRole } = render(<CopyLinkButton opinionId="op with space" />);
    const button = getByRole("button");

    await act(async () => {
      fireEvent.click(button);
      await Promise.resolve();
    });

    const origin = window.location.origin;
    expect(writeText).toHaveBeenCalledWith(
      `${origin}/currents/op%20with%20space`,
    );
  });
});
