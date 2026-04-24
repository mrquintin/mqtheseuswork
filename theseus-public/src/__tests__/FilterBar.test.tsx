// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";

const replace = vi.fn();
let currentSearch = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/currents",
  useSearchParams: () => currentSearch,
}));

import { FilterBar } from "@/app/currents/FilterBar";

beforeEach(() => {
  replace.mockReset();
  currentSearch = new URLSearchParams();
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("FilterBar", () => {
  it("renders with no stance chip active when search params are empty", () => {
    const { getByTestId } = render(<FilterBar topics={["markets"]} />);
    expect(
      getByTestId("filter-stance-agrees").getAttribute("data-active"),
    ).toBe("false");
    expect(
      getByTestId("filter-stance-disagrees").getAttribute("data-active"),
    ).toBe("false");
    expect(
      getByTestId("filter-stance-complicates").getAttribute("data-active"),
    ).toBe("false");
    expect(
      getByTestId("filter-stance-insufficient").getAttribute("data-active"),
    ).toBe("false");
  });

  it("highlights the any-time since preset by default", () => {
    const { getByTestId } = render(<FilterBar topics={[]} />);
    expect(getByTestId("filter-since-any").getAttribute("data-active")).toBe(
      "true",
    );
  });

  it("clicking a stance chip calls router.replace with the new param", () => {
    const { getByTestId } = render(<FilterBar topics={[]} />);
    fireEvent.click(getByTestId("filter-stance-disagrees"));
    expect(replace).toHaveBeenCalledTimes(1);
    const arg = replace.mock.calls[0][0] as string;
    expect(arg).toBe("/currents?stance=disagrees");
  });

  it("clicking an already-active stance chip toggles it off", () => {
    currentSearch = new URLSearchParams("stance=agrees");
    const { getByTestId } = render(<FilterBar topics={[]} />);
    fireEvent.click(getByTestId("filter-stance-agrees"));
    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace.mock.calls[0][0]).toBe("/currents");
  });

  it("selecting a topic sets topic=... in the URL", () => {
    const { getByTestId } = render(
      <FilterBar topics={["markets", "politics"]} />,
    );
    fireEvent.change(getByTestId("filter-topic"), {
      target: { value: "markets" },
    });
    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace.mock.calls[0][0]).toBe("/currents?topic=markets");
  });

  it("debounces search input by 250ms before pushing to the URL", () => {
    const { getByTestId } = render(<FilterBar topics={[]} />);
    const input = getByTestId("filter-search") as HTMLInputElement;

    fireEvent.change(input, { target: { value: "hello" } });
    // Typing alone should not push immediately.
    expect(replace).not.toHaveBeenCalled();

    // Not yet at 250ms.
    vi.advanceTimersByTime(200);
    expect(replace).not.toHaveBeenCalled();

    // Past the debounce window.
    vi.advanceTimersByTime(100);
    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace.mock.calls[0][0]).toBe("/currents?q=hello");
  });

  it("resets the debounce timer when the user keeps typing", () => {
    const { getByTestId } = render(<FilterBar topics={[]} />);
    const input = getByTestId("filter-search") as HTMLInputElement;

    fireEvent.change(input, { target: { value: "he" } });
    vi.advanceTimersByTime(200);
    fireEvent.change(input, { target: { value: "hello" } });
    vi.advanceTimersByTime(200);
    // Still within the second 250ms window — no push yet.
    expect(replace).not.toHaveBeenCalled();

    vi.advanceTimersByTime(100);
    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace.mock.calls[0][0]).toBe("/currents?q=hello");
  });

  it("toggles the chronological <-> by-topic view", () => {
    const { getByTestId } = render(<FilterBar topics={[]} />);
    fireEvent.click(getByTestId("filter-view-toggle"));
    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace.mock.calls[0][0]).toBe("/currents?view=by-topic");
  });
});
