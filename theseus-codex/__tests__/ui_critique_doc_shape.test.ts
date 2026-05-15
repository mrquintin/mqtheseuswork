/**
 * Doc-shape verification for `coding_prompts/UI_CRITIQUE_2026_05_13.md`.
 *
 * This is a *shape* test, not a content test. It guards the structural
 * invariants that prompt 66 (the application pass) depends on:
 *
 *   1. The critique file exists.
 *   2. All six required top-level sections are present.
 *   3. Every finding (ids like F-C1, P-1, D-1, ...) is paired with at
 *      least one revision proposal reference (e.g. "See **R-007**").
 *   4. Every revision id (R-001, R-002, ...) appears as a unique
 *      "### R-NNN" header in the prioritised plan.
 *   5. Every screenshot filename referenced from the critique exists on
 *      disk under `docs/ui-critique/2026-05-13/screenshots/`.
 *
 * The test deliberately lives outside `src/__tests__/` so it is not
 * picked up by the default `vitest run` sweep — it documents the
 * critique's shape but is invoked explicitly by prompt 65's
 * verification step. Vitest's default include glob (configured in
 * `vitest.config.ts` to `src/__tests__/**` and `tests/**`) skips this
 * file; pass `--config=/dev/null` so vitest's built-in defaults pick
 * it up:
 *
 *   cd theseus-codex
 *   npx vitest run --config=/dev/null __tests__/ui_critique_doc_shape.test.ts
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const CRITIQUE_PATH = path.join(
  REPO_ROOT,
  "coding_prompts",
  "UI_CRITIQUE_2026_05_13.md",
);
const SCREENSHOT_DIR = path.join(
  REPO_ROOT,
  "docs",
  "ui-critique",
  "2026-05-13",
  "screenshots",
);

const REQUIRED_SECTIONS = [
  /^##\s+1\.\s+Methodology\b/m,
  /^##\s+2\.\s+Cross-surface findings\b/m,
  /^##\s+3\.\s+Per-surface findings\b/m,
  /^##\s+4\.\s+What is already good\b/m,
  /^##\s+5\.\s+Prioritised revision plan\b/m,
  /^##\s+6\.\s+Things the designer is uncertain about\b/m,
];

function loadCritique(): string {
  expect(
    fs.existsSync(CRITIQUE_PATH),
    `critique file missing at ${CRITIQUE_PATH}`,
  ).toBe(true);
  return fs.readFileSync(CRITIQUE_PATH, "utf8");
}

describe("UI_CRITIQUE_2026_05_13.md — shape", () => {
  it("contains all six required top-level sections", () => {
    const text = loadCritique();
    for (const re of REQUIRED_SECTIONS) {
      expect(text, `missing section matching ${re}`).toMatch(re);
    }
  });

  it("each finding is paired with at least one revision reference", () => {
    const text = loadCritique();
    // Finding ids used in the document:
    //   F-C1..F-C5  (cross-surface)
    //   P-1..P-3    (public home)
    //   L-1..L-3    (login)
    //   D-1..D-3    (dashboard)
    //   K-1..K-3    (knowledge)
    //   Pr-1..Pr-3  (principles)
    //   Cu-1..Cu-3  (currents)
    //   Po-1..Po-3  (portfolio)
    //   Ar-1..Ar-3  (article)
    //   Op-1..Op-3  (ops)
    const findingRe = /\*\*((?:F-C|P-|L-|D-|K-|Pr-|Cu-|Po-|Ar-|Op-)\d+)\.\*\*/g;
    const findings: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = findingRe.exec(text))) findings.push(m[1]);
    expect(
      findings.length,
      "at least one finding should be present",
    ).toBeGreaterThan(0);

    // Each finding block runs from its bolded id up to the next finding
    // bold-id or the next top-level section, whichever comes first.
    // We slice on each finding's position and require that the slice
    // contains at least one "R-NNN" reference (either folded-into or
    // see-R-NNN).
    const indices = [...text.matchAll(findingRe)].map((match) => ({
      id: match[1],
      start: match.index!,
    }));
    indices.push({ id: "__end__", start: text.length });

    for (let i = 0; i < indices.length - 1; i += 1) {
      const slice = text.slice(indices[i].start, indices[i + 1].start);
      expect(
        slice,
        `finding ${indices[i].id} has no paired revision reference (expected an R-NNN mention)`,
      ).toMatch(/\bR-\d{3}\b/);
    }
  });

  it("every revision id appears as a unique '### R-NNN' header", () => {
    const text = loadCritique();
    const headerRe = /^###\s+(R-\d{3})\b/gm;
    const seen = new Set<string>();
    const duplicates: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = headerRe.exec(text))) {
      const id = m[1];
      if (seen.has(id)) duplicates.push(id);
      seen.add(id);
    }
    expect(
      seen.size,
      "at least one R-NNN header should be present",
    ).toBeGreaterThan(0);
    expect(duplicates, `duplicate revision ids: ${duplicates.join(", ")}`).toEqual(
      [],
    );

    // Every R-NNN referenced from the body must exist as a header. This
    // catches typos like "R-O01" or "R-12" that wouldn't resolve.
    const referenced = new Set<string>();
    const refRe = /\bR-\d{3}\b/g;
    while ((m = refRe.exec(text))) referenced.add(m[0]);
    const missing = [...referenced].filter((id) => !seen.has(id));
    expect(missing, `revision ids referenced but not defined: ${missing.join(", ")}`).toEqual(
      [],
    );
  });

  it("every screenshot referenced in the critique exists on disk", () => {
    const text = loadCritique();
    const shotRe = /\b([a-z0-9-]+\.png)\b/g;
    const referenced = new Set<string>();
    let m: RegExpExecArray | null;
    while ((m = shotRe.exec(text))) referenced.add(m[1]);
    expect(
      referenced.size,
      "critique should reference at least one screenshot",
    ).toBeGreaterThan(0);

    const missing: string[] = [];
    for (const filename of referenced) {
      const onDisk = path.join(SCREENSHOT_DIR, filename);
      if (!fs.existsSync(onDisk)) missing.push(filename);
    }
    expect(
      missing,
      `screenshots referenced but missing from disk: ${missing.join(", ")}`,
    ).toEqual([]);
  });
});
