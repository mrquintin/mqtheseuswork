import { describe, it, expect } from "vitest";
import UploadRowDetail, { humanMethod } from "@/components/UploadRowDetail";
import UploadRetryButton from "@/components/UploadRetryButton";
import type { ReactElement, ReactNode } from "react";

/**
 * UploadRowDetail is a pure server component so we invoke it as a
 * function and walk the returned tree. The retry button is rendered
 * as a React element (the client bundle will hydrate it at runtime);
 * here we assert the element type and its `uploadId` prop so the test
 * stays fully in node-env without jsdom.
 */

type ElementNode = ReactElement<{ [key: string]: unknown; children?: ReactNode }>;

function isElement(node: ReactNode): node is ElementNode {
  return (
    typeof node === "object" &&
    node !== null &&
    "props" in (node as object) &&
    "type" in (node as object)
  );
}

function flatten(children: ReactNode): ReactNode[] {
  if (children === null || children === undefined || children === false) return [];
  if (Array.isArray(children)) return children.flatMap(flatten);
  return [children];
}

function allText(node: ReactNode): string {
  const out: string[] = [];
  const stack = flatten(node);
  while (stack.length) {
    const n = stack.shift();
    if (typeof n === "string" || typeof n === "number") {
      out.push(String(n));
    } else if (isElement(n)) {
      stack.unshift(...flatten(n.props.children));
    }
  }
  return out.join(" ");
}

function findElement(
  root: ReactNode,
  pred: (n: ElementNode) => boolean,
): ElementNode | null {
  const stack = flatten(root);
  while (stack.length) {
    const n = stack.shift();
    if (!isElement(n)) continue;
    if (pred(n)) return n;
    stack.unshift(...flatten(n.props.children));
  }
  return null;
}

describe("UploadRowDetail", () => {
  it("renders a humanized extractionMethod caption when status='ingested'", () => {
    const el = UploadRowDetail({
      upload: {
        id: "up_1",
        status: "ingested",
        extractionMethod: "faster-whisper",
        errorMessage: null,
      },
    });
    expect(el).not.toBeNull();
    expect(allText(el)).toContain("transcribed locally (faster-whisper)");
  });

  it("renders nothing for ingested rows with no extractionMethod", () => {
    const el = UploadRowDetail({
      upload: {
        id: "up_2",
        status: "ingested",
        extractionMethod: null,
        errorMessage: null,
      },
    });
    expect(el).toBeNull();
  });

  it("renders nothing for in-flight statuses (pending/processing/…)", () => {
    for (const status of ["pending", "extracting", "awaiting_ingest", "processing"]) {
      const el = UploadRowDetail({
        upload: {
          id: "up_3",
          status,
          extractionMethod: null,
          errorMessage: null,
        },
      });
      expect(el, `expected null for status=${status}`).toBeNull();
    }
  });

  it("renders an expandable error summary for failed rows", () => {
    const longMsg =
      "unsupported_mime: application/zip — the Codex only extracts text, audio, and PDF today. Convert the archive and re-upload.";
    const el = UploadRowDetail({
      upload: {
        id: "up_4",
        status: "failed",
        errorMessage: longMsg,
        extractionMethod: null,
      },
    }) as ElementNode;
    expect(el).not.toBeNull();
    const summary = findElement(el, (n) => n.type === "summary");
    expect(summary).not.toBeNull();
    expect(allText(summary)).toContain("unsupported_mime:");
    const pre = findElement(el, (n) => n.type === "pre");
    expect(pre).not.toBeNull();
    expect(allText(pre)).toBe(longMsg);
  });

  it("truncates the summary but keeps the full message in the <pre>", () => {
    const huge = "x".repeat(500);
    const el = UploadRowDetail({
      upload: {
        id: "up_5",
        status: "failed",
        errorMessage: huge,
        extractionMethod: null,
      },
    }) as ElementNode;
    const summary = findElement(el, (n) => n.type === "summary");
    const pre = findElement(el, (n) => n.type === "pre");
    const summaryText = allText(summary);
    expect(summaryText.endsWith("…")).toBe(true);
    expect(summaryText.length).toBeLessThanOrEqual(141);
    expect(allText(pre)).toBe(huge);
  });

  it("embeds an UploadRetryButton bound to the upload id for failed rows", () => {
    const el = UploadRowDetail({
      upload: {
        id: "up_6",
        status: "failed",
        errorMessage: "boom",
        extractionMethod: null,
      },
    }) as ElementNode;
    const btn = findElement(el, (n) => n.type === UploadRetryButton);
    expect(btn).not.toBeNull();
    expect((btn as ElementNode).props.uploadId).toBe("up_6");
  });

  it("supplies a sensible fallback for a failed row with no errorMessage", () => {
    const el = UploadRowDetail({
      upload: {
        id: "up_7",
        status: "failed",
        errorMessage: null,
        extractionMethod: null,
      },
    }) as ElementNode;
    expect(allText(el)).toContain("Processing failed");
  });
});

describe("humanMethod", () => {
  it("maps every known extractor token", () => {
    expect(humanMethod("passthrough")).toBe("stored as text");
    expect(humanMethod("faster-whisper")).toContain("faster-whisper");
    expect(humanMethod("openai-whisper-1")).toContain("OpenAI");
    expect(humanMethod("pypdf")).toContain("pypdf");
    expect(humanMethod("ocrmypdf")).toContain("ocrmypdf");
  });

  it("falls back to a generic phrase for unknown tokens", () => {
    expect(humanMethod("some-new-extractor")).toBe(
      "extracted via some-new-extractor",
    );
  });
});
