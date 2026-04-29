import { describe, expect, it } from "vitest";

import { relativeTime } from "@/lib/relativeTime";

describe("relativeTime", () => {
  const now = new Date("2026-04-29T12:00:00.000Z").getTime();

  it.each([
    [5_000, "5s ago"],
    [59_000, "59s ago"],
    [60_000, "1m ago"],
    [90 * 60_000, "1h ago"],
    [25 * 60 * 60_000, "1d ago"],
    [8 * 24 * 60 * 60_000, "8d ago"],
  ])("formats %i milliseconds ago as %s", (elapsed, expected) => {
    expect(relativeTime(new Date(now - elapsed).toISOString(), now)).toBe(expected);
  });
});
