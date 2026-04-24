// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearSessionId,
  loadSessionId,
  saveSessionId,
} from "@/lib/followupSession";

afterEach(() => {
  try {
    sessionStorage.clear();
  } catch {
    /* storage may be stubbed out */
  }
  vi.unstubAllGlobals();
});

describe("followupSession", () => {
  it("round-trips a session id in jsdom's sessionStorage", () => {
    expect(loadSessionId("op-1")).toBeNull();
    saveSessionId("op-1", "sess-abc");
    expect(loadSessionId("op-1")).toBe("sess-abc");
  });

  it("namespaces by opinion id", () => {
    saveSessionId("op-1", "sess-1");
    saveSessionId("op-2", "sess-2");
    expect(loadSessionId("op-1")).toBe("sess-1");
    expect(loadSessionId("op-2")).toBe("sess-2");
  });

  it("clears a stored session id", () => {
    saveSessionId("op-1", "sess-abc");
    clearSessionId("op-1");
    expect(loadSessionId("op-1")).toBeNull();
  });

  it("no-ops when sessionStorage is unavailable", () => {
    vi.stubGlobal("sessionStorage", undefined);
    expect(() => saveSessionId("op-1", "sess-abc")).not.toThrow();
    expect(loadSessionId("op-1")).toBeNull();
    expect(() => clearSessionId("op-1")).not.toThrow();
  });

  it("tolerates sessionStorage throwing (quota / denied)", () => {
    const throwing = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => {
        throw new Error("denied");
      },
    };
    vi.stubGlobal("sessionStorage", throwing);
    expect(() => saveSessionId("op-1", "sess-abc")).not.toThrow();
    expect(loadSessionId("op-1")).toBeNull();
    expect(() => clearSessionId("op-1")).not.toThrow();
  });
});
