import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { theseusIdentity } from "@/content/theseusIdentity";

function wordCount(value: string): number {
  return value.trim().split(/\s+/).filter(Boolean).length;
}

function sourceFile(relativePath: string): string {
  return readFileSync(
    fileURLToPath(new URL(relativePath, import.meta.url)),
    "utf8",
  );
}

describe("theseusIdentity", () => {
  it("keeps the public identity copy inside the documented bounds", () => {
    expect(theseusIdentity.oneLine.length).toBeLessThanOrEqual(120);
    expect(wordCount(theseusIdentity.oneLine)).toBeLessThanOrEqual(16);
    expect(wordCount(theseusIdentity.manifesto.body)).toBeGreaterThanOrEqual(
      300,
    );
    expect(wordCount(theseusIdentity.manifesto.body)).toBeLessThanOrEqual(600);
  });

  it("defines every axiom with a name and elaboration", () => {
    expect(theseusIdentity.axioms).toHaveLength(3);

    for (const axiom of theseusIdentity.axioms) {
      expect(axiom.name.trim()).not.toBe("");
      expect(axiom.elaboration.trim()).not.toBe("");
    }
  });

  it("keeps institutional copy out of the homepage and about page", () => {
    const files = ["../app/page.tsx", "../app/about/page.tsx"];
    const offenders = files.flatMap((file) =>
      sourceFile(file)
        .split("\n")
        .map((line, index) => ({ file, line, lineNumber: index + 1 }))
        .filter(({ line }) => !line.trimStart().startsWith("import "))
        .filter(({ line }) => line.includes("intellectual capital")),
    );

    expect(offenders).toEqual([]);
  });
});
