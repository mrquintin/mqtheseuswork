import { describe, it, expect } from "vitest";
import {
  stripNullBytes,
  sanitizeText,
  sanitizeAndCap,
  sanitizeDeep,
} from "@/lib/sanitizeText";

describe("sanitizeText", () => {
  it("strips NUL bytes — the bug that killed uploads", () => {
    const input = "hello\u0000world";
    expect(sanitizeText(input)).toBe("helloworld");
  });

  it("preserves tab, newline, and carriage return", () => {
    const input = "one\ttwo\nthree\r\nfour";
    expect(sanitizeText(input)).toBe(input);
  });

  it("strips other C0 control chars", () => {
    const input = "bad\x01\x02\x03\x1Fcontrol";
    expect(sanitizeText(input)).toBe("badcontrol");
  });

  it("strips the BOM", () => {
    const input = "\uFEFFreal text";
    expect(sanitizeText(input)).toBe("real text");
  });

  it("strips lone surrogate halves", () => {
    const input = "\uD800hello\uDC00world";
    expect(sanitizeText(input)).toBe("helloworld");
  });

  it("preserves valid emoji / surrogate pairs", () => {
    // "👋" is U+1F44B (waving hand), encoded as surrogate pair in UTF-16
    const input = "hi 👋 there";
    expect(sanitizeText(input)).toBe(input);
  });

  it("handles null and undefined without throwing", () => {
    expect(sanitizeText(null)).toBe("");
    expect(sanitizeText(undefined)).toBe("");
    expect(sanitizeText("")).toBe("");
  });

  it("is idempotent", () => {
    const messy = "foo\u0000\x01bar";
    const once = sanitizeText(messy);
    const twice = sanitizeText(once);
    expect(once).toBe(twice);
  });
});

describe("stripNullBytes", () => {
  it("only strips NUL, preserves everything else", () => {
    const input = "\x01keep\u0000me\x1F";
    expect(stripNullBytes(input)).toBe("\x01keepme\x1F");
  });
});

describe("sanitizeAndCap", () => {
  it("caps long strings after sanitization", () => {
    const input = "a".repeat(3_000_000);
    const out = sanitizeAndCap(input);
    expect(out.length).toBe(2_000_000);
  });

  it("respects a custom cap", () => {
    const input = "a".repeat(500);
    expect(sanitizeAndCap(input, 100).length).toBe(100);
  });

  it("strips NUL bytes before capping so we don't waste cap budget", () => {
    const input = "\u0000".repeat(1000) + "real";
    expect(sanitizeAndCap(input, 100)).toBe("real");
  });
});

describe("sanitizeDeep", () => {
  it("walks objects, arrays, and strings; leaves primitives alone", () => {
    const messy = {
      title: "clean\u0000dirty",
      count: 42,
      enabled: true,
      tags: ["one\u0000", "two"],
      nested: { body: "deep\u0000problem" },
      nothing: null,
    };
    const cleaned = sanitizeDeep(messy);
    expect(cleaned).toEqual({
      title: "cleandirty",
      count: 42,
      enabled: true,
      tags: ["one", "two"],
      nested: { body: "deepproblem" },
      nothing: null,
    });
  });
});
