import { describe, expect, it } from "vitest";
import { relativeTime } from "@/lib/relativeTime";

const NOW = new Date("2026-04-20T12:00:00Z").getTime();

function iso(offsetMs: number): string {
  return new Date(NOW - offsetMs).toISOString();
}

describe("relativeTime", () => {
  it("renders seconds for under a minute", () => {
    expect(relativeTime(iso(5_000), NOW)).toBe("5s ago");
    expect(relativeTime(iso(59_000), NOW)).toBe("59s ago");
  });

  it("rolls over to minutes at 60s", () => {
    expect(relativeTime(iso(60_000), NOW)).toBe("1m ago");
  });

  it("renders minutes up to an hour", () => {
    // 90 minutes = 1.5h → rounds to 2h
    expect(relativeTime(iso(90 * 60_000), NOW)).toBe("2h ago");
    expect(relativeTime(iso(30 * 60_000), NOW)).toBe("30m ago");
  });

  it("renders hours up to a day", () => {
    // 25h → rounds to 1d
    expect(relativeTime(iso(25 * 3600_000), NOW)).toBe("1d ago");
    expect(relativeTime(iso(5 * 3600_000), NOW)).toBe("5h ago");
  });

  it("renders days beyond 24h", () => {
    expect(relativeTime(iso(8 * 86_400_000), NOW)).toBe("8d ago");
  });

  it("clamps to at least 1s", () => {
    expect(relativeTime(iso(0), NOW)).toBe("1s ago");
  });
});
