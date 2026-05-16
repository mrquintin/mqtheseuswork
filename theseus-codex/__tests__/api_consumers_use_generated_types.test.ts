/**
 * Frontend half of the API type-contract gate (Round 19).
 *
 * The Python-side test (`tests/static/test_api_types_in_sync.py`)
 * already guarantees the committed `_generated/api/` bundle matches
 * the FastAPI response models byte-for-byte. This test handles the
 * mirror failure mode: a frontend module redefining a generated
 * shape locally instead of importing from `_generated/api`, which
 * lets the two drift apart silently.
 *
 * Rules enforced here:
 *
 * 1. `_generated/api/index.ts` must exist and re-export at least one
 *    type. (If the generator silently emits zero files, this catches
 *    it.)
 * 2. Any TS file under `src/lib/` or `src/app/api/` that re-declares
 *    a *generated* interface name must instead import it from
 *    `@/lib/_generated/api`. Accidental hand-rolled duplicates are
 *    the precise failure mode this guards.
 * 3. Allowlisted proxy routes (SSE streams, file downloads, OG
 *    image renderers) are exempt from rule 2 — they legitimately
 *    don't deserialize the upstream body.
 */

import { describe, expect, it } from "vitest";
import { promises as fs } from "node:fs";
import path from "node:path";

const REPO_ROOT = path.resolve(__dirname, "..");
const GENERATED_DIR = path.join(REPO_ROOT, "src", "lib", "_generated", "api");
const SCAN_ROOTS = [
  path.join(REPO_ROOT, "src", "lib"),
  path.join(REPO_ROOT, "src", "app", "api"),
];

/**
 * Routes / modules that legitimately do not deserialize the upstream
 * JSON body — pure byte passthroughs, SSE streams, OG image renderers,
 * file downloads. They keep the bytes opaque on purpose; no typed
 * shape applies.
 */
const ALLOWLIST_SUBSTRINGS = [
  "/stream/",
  "/og/",
  "/upload/",
  "/sse/",
];

/**
 * Files that *currently* re-declare a generated shape locally and
 * have not yet been migrated to import from `@/lib/_generated/api`.
 * Each entry is migration debt: the file should eventually delete its
 * local declaration and import the canonical type instead.
 *
 * New entries to this list require a comment justifying the seam.
 * Removing entries (after migration) is unconditionally good.
 *
 * Tracked as part of the Round-19 type-contract rollout; the
 * follow-up prompt physically migrates the consumers.
 */
const PRE_EXISTING_DUPLICATE_DECLARATIONS = new Set<string>([
  "src/lib/conclusionsRead.ts → PublicCitation",
  "src/lib/currentsTypes.ts → PublicCitation",
  "src/lib/currentsTypes.ts → PublicCurrentEvent",
  "src/lib/currentsTypes.ts → PublicFollowupMessage",
  "src/lib/currentsTypes.ts → PublicOpinion",
  "src/lib/currentsTypes.ts → PublicSource",
  "src/lib/forecastPortfolioData.ts → TraceGateResult",
  "src/lib/forecastPortfolioData.ts → TracePrinciple",
  "src/lib/forecastsTypes.ts → CalibrationBucket",
  "src/lib/forecastsTypes.ts → OperatorBet",
  "src/lib/forecastsTypes.ts → PortfolioPoint",
  "src/lib/forecastsTypes.ts → PortfolioSummary",
  "src/lib/forecastsTypes.ts → PublicBet",
  "src/lib/forecastsTypes.ts → PublicFollowupMessage",
  "src/lib/forecastsTypes.ts → PublicForecast",
  "src/lib/forecastsTypes.ts → PublicForecastCitation",
  "src/lib/forecastsTypes.ts → PublicForecastSource",
  "src/lib/forecastsTypes.ts → PublicMarket",
  "src/lib/forecastsTypes.ts → PublicResolution",
]);

async function* walk(dir: string): AsyncGenerator<string> {
  let entries: import("node:fs").Dirent[];
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      // Skip the generated tree itself — it intentionally *defines*
      // the names we're searching for.
      if (full === GENERATED_DIR) continue;
      if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
      yield* walk(full);
    } else if (
      entry.isFile() &&
      (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx"))
    ) {
      yield full;
    }
  }
}

async function generatedTypeNames(): Promise<string[]> {
  const indexBody = await fs.readFile(path.join(GENERATED_DIR, "index.ts"), "utf8");
  const names = new Set<string>();
  // Match: `export type { Foo, Bar } from "./module";`
  const re = /export\s+type\s*\{([^}]+)\}\s*from\s*"\.\/[^"]+";/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(indexBody)) !== null) {
    for (const part of m[1].split(",")) {
      const trimmed = part.trim().split(/\s+as\s+/)[0].trim();
      if (trimmed) names.add(trimmed);
    }
  }
  return Array.from(names).sort();
}

function isAllowlisted(file: string): boolean {
  const rel = file.split(path.sep).join("/");
  return ALLOWLIST_SUBSTRINGS.some((s) => rel.includes(s));
}

describe("API type contract — frontend consumers", () => {
  it("the generated index re-exports at least one shape", async () => {
    const names = await generatedTypeNames();
    expect(names.length).toBeGreaterThan(0);
  });

  it("no source file re-declares a generated type locally", async () => {
    const generated = await generatedTypeNames();
    const offenders: string[] = [];

    // Pre-compile one regex per type name. We require the name to
    // appear as an *interface* or *type-alias* declaration; uses
    // in field positions don't count.
    const declRes = generated.map(
      (name) =>
        new RegExp(
          `^\\s*export\\s+(?:interface|type)\\s+${name}\\b`,
          "m",
        ),
    );

    for (const root of SCAN_ROOTS) {
      for await (const file of walk(root)) {
        if (isAllowlisted(file)) continue;
        const body = await fs.readFile(file, "utf8");
        for (let i = 0; i < generated.length; i += 1) {
          if (declRes[i].test(body)) {
            // It's only a violation if the file *also* fails to
            // import the canonical name from _generated/api. Some
            // legacy files re-export the generated type by name with
            // its own jsdoc — that's fine if they pass through.
            const importRe = new RegExp(
              `from\\s+"@/lib/_generated/api(?:/[^"]+)?"`,
            );
            if (!importRe.test(body)) {
              const rel = path.relative(REPO_ROOT, file).split(path.sep).join("/");
              const key = `${rel} → ${generated[i]}`;
              if (!PRE_EXISTING_DUPLICATE_DECLARATIONS.has(key)) {
                offenders.push(key);
              }
            }
          }
        }
      }
    }

    expect(
      offenders,
      `These files declare a generated shape locally instead of importing\n` +
        `from @/lib/_generated/api. Replace the local declaration with an\n` +
        `import to keep the frontend in lock-step with the FastAPI schema:\n\n` +
        offenders.map((o) => `  - ${o}`).join("\n"),
    ).toEqual([]);
  });

  it("every generated module file exists on disk", async () => {
    const index = await fs.readFile(
      path.join(GENERATED_DIR, "index.ts"),
      "utf8",
    );
    const moduleRe = /from\s+"\.\/([^"]+)";/g;
    const missing: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = moduleRe.exec(index)) !== null) {
      const target = path.join(GENERATED_DIR, `${m[1]}.ts`);
      try {
        await fs.access(target);
      } catch {
        missing.push(m[1]);
      }
    }
    expect(missing).toEqual([]);
  });
});
