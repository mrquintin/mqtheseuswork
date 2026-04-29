import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

describe("followupSession", () => {
  let storage: MemoryStorage;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-29T12:00:00.000Z"));
    storage = new MemoryStorage();
    vi.stubGlobal("sessionStorage", storage);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("saveSession + loadSession round-trip through sessionStorage", async () => {
    const { followupSessionKey, loadSession, saveSession } = await import("@/lib/followupSession");

    saveSession("opinion-1", "session-abc");

    expect(loadSession("opinion-1")).toBe("session-abc");
    expect(storage.getItem(followupSessionKey("opinion-1"))).toContain('"session_id":"session-abc"');
  });

  it("respects the 24h TTL and clears expired keys", async () => {
    const { followupSessionKey, loadSession, saveSession } = await import("@/lib/followupSession");

    saveSession("opinion-1", "session-expiring");
    vi.setSystemTime(new Date("2026-04-30T12:00:00.001Z"));

    expect(loadSession("opinion-1")).toBeNull();
    expect(storage.getItem(followupSessionKey("opinion-1"))).toBeNull();
  });
});
