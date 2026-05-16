/**
 * Identity copy module — shape tests.
 *
 * Guards the canonical "Philosopher in a Box" strings that the
 * homepage, About page, and pitch deck depend on. The companion lint
 * script `scripts/check_no_inline_identity_duplicates.py` enforces the
 * other side of the contract: that no TS/TSX file outside the identity
 * module hardcodes the same strings.
 *
 * Run with:
 *   cd theseus-codex
 *   npx vitest run --config=/dev/null __tests__/identity_copy.test.ts
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

import {
  CANONICAL_IDENTITY_STRINGS,
  THESEUS_AXIOMS,
  THESEUS_BET_DOMAINS,
  THESEUS_IDENTITY_HEADINGS,
  THESEUS_LOGIC_VS_QUANT,
  THESEUS_NOT_COMMERCIAL,
  THESEUS_ONE_PARAGRAPH,
  THESEUS_PIPELINE_ASCII,
  THESEUS_TAGLINE,
} from "../src/lib/copy/identity";

describe("identity copy module — required exports", () => {
  it("exports the tagline verbatim", () => {
    expect(THESEUS_TAGLINE).toBe("A philosopher in a box.");
  });

  it("exports the one-paragraph statement with all four canonical clauses", () => {
    expect(THESEUS_ONE_PARAGRAPH).toMatch(/philosopher in a box/);
    expect(THESEUS_ONE_PARAGRAPH).toMatch(/curated corpus/);
    expect(THESEUS_ONE_PARAGRAPH).toMatch(/Renaissance Technologies/);
    expect(THESEUS_ONE_PARAGRAPH).toMatch(/machine is our edge/);
  });

  it("exports the logic-vs-quant framing naming the four stack layers", () => {
    expect(THESEUS_LOGIC_VS_QUANT).toMatch(/corpus/i);
    expect(THESEUS_LOGIC_VS_QUANT).toMatch(/synthesizer/i);
    expect(THESEUS_LOGIC_VS_QUANT).toMatch(/principle/i);
    expect(THESEUS_LOGIC_VS_QUANT).toMatch(/algorithm/i);
  });

  it("exports the not-commercial declaration verbatim", () => {
    expect(THESEUS_NOT_COMMERCIAL).toBe(
      "Theseus is not a SaaS product. The reasoning architecture is our edge.",
    );
  });

  it("exports exactly three axioms, each with name + summary + elaboration", () => {
    expect(THESEUS_AXIOMS).toHaveLength(3);
    const names = THESEUS_AXIOMS.map((axiom) => axiom.name);
    expect(names).toEqual(["Progress", "Rigor", "Camaraderie"]);
    for (const axiom of THESEUS_AXIOMS) {
      expect(axiom.summary.length, `${axiom.name} summary missing`).toBeGreaterThan(
        0,
      );
      expect(
        axiom.elaboration.length,
        `${axiom.name} elaboration missing`,
      ).toBeGreaterThan(40);
    }
  });

  it("exports the bet domains from the meeting", () => {
    const joined = THESEUS_BET_DOMAINS.join(" ").toLowerCase();
    expect(joined).toMatch(/equit/);
    expect(joined).toMatch(/prediction market/);
    expect(joined).toMatch(/advisory/);
    expect(joined).toMatch(/scientific/);
    expect(joined).toMatch(/private/);
  });

  it("exports the pipeline ASCII diagram with every named stage", () => {
    for (const token of [
      "corpus",
      "synthesizer",
      "principles",
      "algorithms",
      "live observations",
      "conclusions",
      "memos",
      "portfolio agent",
      "bet",
    ]) {
      expect(
        THESEUS_PIPELINE_ASCII.toLowerCase(),
        `pipeline diagram missing '${token}'`,
      ).toContain(token);
    }
  });

  it("exports the heading variants used on the homepage", () => {
    expect(THESEUS_IDENTITY_HEADINGS.machineRail).toBe("The machine.");
    expect(THESEUS_IDENTITY_HEADINGS.liveActivity).toMatch(/machine.*thinking/i);
    expect(THESEUS_IDENTITY_HEADINGS.readTheDeck).toMatch(/deck/i);
  });

  it("CANONICAL_IDENTITY_STRINGS contains exactly the four lint-tracked strings", () => {
    expect(CANONICAL_IDENTITY_STRINGS).toHaveLength(4);
    expect(CANONICAL_IDENTITY_STRINGS).toContain(THESEUS_TAGLINE);
    expect(CANONICAL_IDENTITY_STRINGS).toContain(THESEUS_ONE_PARAGRAPH);
    expect(CANONICAL_IDENTITY_STRINGS).toContain(THESEUS_LOGIC_VS_QUANT);
    expect(CANONICAL_IDENTITY_STRINGS).toContain(THESEUS_NOT_COMMERCIAL);
  });
});

describe("identity copy lint contract", () => {
  const repoRoot = path.resolve(__dirname, "..", "..");
  const lintScript = path.join(
    repoRoot,
    "theseus-codex",
    "scripts",
    "check_no_inline_identity_duplicates.py",
  );

  it("the companion lint script is checked in and executable in spirit", () => {
    expect(fs.existsSync(lintScript), `lint script missing at ${lintScript}`).toBe(
      true,
    );
    const source = fs.readFileSync(lintScript, "utf8");
    expect(source).toMatch(/CANONICAL/);
    expect(source).toMatch(/identity\.ts/);
  });

  it("the identity module itself is the only place the canonical strings appear in src/", () => {
    const srcRoot = path.join(repoRoot, "theseus-codex", "src");
    const identityPath = path.join(srcRoot, "lib", "copy", "identity.ts");
    expect(fs.existsSync(identityPath)).toBe(true);

    const offenders: string[] = [];
    walk(srcRoot, (filePath) => {
      if (filePath === identityPath) return;
      if (!filePath.endsWith(".ts") && !filePath.endsWith(".tsx")) return;
      const text = fs.readFileSync(filePath, "utf8");
      for (const canonical of CANONICAL_IDENTITY_STRINGS) {
        if (text.includes(canonical)) {
          offenders.push(`${path.relative(repoRoot, filePath)} :: ${canonical.slice(0, 60)}…`);
        }
      }
    });
    expect(
      offenders,
      `inline canonical-string duplicates detected:\n${offenders.join("\n")}`,
    ).toEqual([]);
  });
});

function walk(dir: string, visit: (filePath: string) => void): void {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full, visit);
    } else if (entry.isFile()) {
      visit(full);
    }
  }
}
