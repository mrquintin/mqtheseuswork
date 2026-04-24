// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import React from "react";
import { cleanup, render } from "@testing-library/react";
import { highlightFirst } from "@/lib/highlight";

afterEach(() => {
  cleanup();
});

// Wraps the return value in a div so we can inspect the rendered DOM.
function renderNode(node: React.ReactNode) {
  return render(React.createElement("div", null, node));
}

describe("highlightFirst", () => {
  it("wraps the first case-insensitive match in a <mark>", () => {
    const { container } = renderNode(highlightFirst("ABC def ABC", "def"));
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("def");
  });

  it("normalizes whitespace when matching (collapses runs to single space)", () => {
    const { container } = renderNode(
      highlightFirst("Hello  world", "hello world"),
    );
    const mark = container.querySelector("mark");
    expect(mark).not.toBeNull();
    // The highlighted span should cover the original text including the
    // double-space, because both sides normalize to "hello world".
    expect(mark!.textContent).toBe("Hello  world");
  });

  it("is case-insensitive on the needle", () => {
    const { container } = renderNode(
      highlightFirst("The Fed cut rates", "FED CUT"),
    );
    const mark = container.querySelector("mark");
    expect(mark).not.toBeNull();
    expect(mark!.textContent).toBe("Fed cut");
  });

  it("returns the haystack unchanged when there is no match", () => {
    const { container } = renderNode(
      highlightFirst("Hello world", "nonexistent"),
    );
    expect(container.querySelector("mark")).toBeNull();
    expect(container.textContent).toBe("Hello world");
  });

  it("returns the haystack unchanged on an empty needle", () => {
    const { container } = renderNode(highlightFirst("Hello world", ""));
    expect(container.querySelector("mark")).toBeNull();
    expect(container.textContent).toBe("Hello world");
  });

  it("returns an empty string unchanged on an empty haystack", () => {
    const { container } = renderNode(highlightFirst("", "abc"));
    expect(container.querySelector("mark")).toBeNull();
    expect(container.textContent).toBe("");
  });

  it("never introduces a <script> even when the needle looks like markup", () => {
    const hostile = "<script>alert(1)</script>";
    const { container } = renderNode(highlightFirst(hostile, "script"));
    expect(container.querySelector("script")).toBeNull();
    // The literal angle brackets are preserved as text.
    expect(container.textContent).toBe(hostile);
  });

  it("only highlights the first occurrence", () => {
    const { container } = renderNode(
      highlightFirst("repeat repeat repeat", "repeat"),
    );
    expect(container.querySelectorAll("mark")).toHaveLength(1);
  });
});
