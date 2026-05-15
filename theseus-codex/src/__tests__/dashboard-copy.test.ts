/**
 * Lint — founder-facing dashboard copy must stay centralized.
 *
 * The Round 20 dashboard terminology pass replaced four founder-facing
 * phrases ("Attention" / "Open Question" / "Snooze" / "Dismiss"). The
 * surviving three live in `src/lib/copy/dashboard.ts`; components
 * import the `DASHBOARD_COPY` object and reference its fields rather
 * than inlining the strings. This test enforces the contract: if a
 * component file (or anything else under `src/` that is not the copy
 * module itself) contains one of the literals, the suite fails — the
 * fix is to import the constant.
 *
 * See `docs/operator/dashboard_terminology.md` for the rationale.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  DASHBOARD_COPY,
  DASHBOARD_COPY_LITERALS,
} from "@/lib/copy/dashboard";

// Walk `src/` and collect every TS/TSX file. Tests, the copy module
// itself, and *.snap files are exempt — tests legitimately assert on
// the user-visible copy, the copy module is the canonical home, and
// snap files mirror rendered output.
function listSourceFiles(root: string): string[] {
  const out: string[] = [];
  const skipDir = new Set([
    "node_modules",
    ".next",
    "__snapshots__",
    "_generated",
  ]);
  function walk(dir: string) {
    for (const entry of readdirSync(dir)) {
      if (skipDir.has(entry)) continue;
      const full = path.join(dir, entry);
      const stat = statSync(full);
      if (stat.isDirectory()) {
        walk(full);
      } else if (
        (entry.endsWith(".ts") || entry.endsWith(".tsx")) &&
        !entry.endsWith(".d.ts")
      ) {
        out.push(full);
      }
    }
  }
  walk(root);
  return out;
}

const SRC_ROOT = path.resolve(__dirname, "..");
const COPY_MODULE = path.resolve(SRC_ROOT, "lib/copy/dashboard.ts");
const TESTS_ROOT = path.resolve(SRC_ROOT, "__tests__");

describe("dashboard copy centralization", () => {
  it("DASHBOARD_COPY exposes the four founder-facing strings", () => {
    // Sanity check: if any field is removed from the copy module, the
    // contract this lint enforces is no longer meaningful — fail loud.
    expect(DASHBOARD_COPY.hideForNow).toMatch(/Hide for now/);
    expect(DASHBOARD_COPY.hidePermanently).toBe("Hide permanently");
    expect(DASHBOARD_COPY.unresolvedResearchThread).toBe(
      "Unresolved research thread",
    );
    expect(DASHBOARD_COPY_LITERALS.length).toBe(3);
  });

  it("no component or library file inlines the centralized literals", () => {
    const files = listSourceFiles(SRC_ROOT).filter((file) => {
      if (file === COPY_MODULE) return false;
      // Tests legitimately reference the literals when asserting on
      // rendered DOM. They are not founder-facing surfaces.
      if (file.startsWith(TESTS_ROOT)) return false;
      return true;
    });

    const offenders: { file: string; literal: string; line: number }[] = [];
    for (const file of files) {
      const content = readFileSync(file, "utf8");
      const lines = content.split("\n");
      for (const literal of DASHBOARD_COPY_LITERALS) {
        for (let i = 0; i < lines.length; i++) {
          if (lines[i].includes(literal)) {
            offenders.push({
              file: path.relative(SRC_ROOT, file),
              literal,
              line: i + 1,
            });
          }
        }
      }
    }

    // Build a readable failure so a future contributor sees exactly
    // where to import `DASHBOARD_COPY` instead of inlining.
    if (offenders.length > 0) {
      const detail = offenders
        .map((o) => `  ${o.file}:${o.line} — "${o.literal}"`)
        .join("\n");
      throw new Error(
        `Dashboard copy must be imported from @/lib/copy/dashboard, not inlined:\n${detail}`,
      );
    }

    expect(offenders).toEqual([]);
  });
});
