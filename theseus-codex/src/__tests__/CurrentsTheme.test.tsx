import { readFileSync } from "fs";
import { fileURLToPath } from "url";

import { describe, expect, it } from "vitest";

type ThemeName = "dark" | "light";

function globalsCss(): string {
  const cssPath = fileURLToPath(new URL("../app/globals.css", import.meta.url));
  return readFileSync(cssPath, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
}

function declarationsForTheme(css: string, theme: ThemeName): Map<string, string> {
  const declarations = new Map<string, string>();
  const blockPattern = /(:root|\[data-theme="light"\])\s*\{(?<body>[^}]*)\}/g;
  let block: RegExpExecArray | null;

  while ((block = blockPattern.exec(css)) !== null) {
    const selector = block[1];
    if (selector !== ":root" && theme !== "light") continue;

    const body = block.groups?.body ?? "";
    const declarationPattern = /(?<name>--[-\w]+)\s*:\s*(?<value>[^;]+);/g;
    let declaration: RegExpExecArray | null;
    while ((declaration = declarationPattern.exec(body)) !== null) {
      const name = declaration.groups?.name;
      const value = declaration.groups?.value?.trim();
      if (name && value) declarations.set(name, value);
    }
  }

  return declarations;
}

function resolveToken(
  declarations: Map<string, string>,
  name: string,
  seen = new Set<string>(),
): string {
  if (seen.has(name)) throw new Error(`Circular CSS token reference: ${name}`);
  seen.add(name);

  const value = declarations.get(name);
  if (!value) throw new Error(`Missing CSS token: ${name}`);

  return value.replace(/var\((--[-\w]+)\)/g, (_, referenced: string) =>
    resolveToken(declarations, referenced, seen),
  );
}

function themeSnapshot(theme: ThemeName) {
  const declarations = declarationsForTheme(globalsCss(), theme);
  return {
    currentsBg: resolveToken(declarations, "--currents-bg"),
    currentsBgElevated: resolveToken(declarations, "--currents-bg-elevated"),
    currentsBorder: resolveToken(declarations, "--currents-border"),
    currentsMuted: resolveToken(declarations, "--currents-muted"),
    ink: resolveToken(declarations, "--ink"),
    parchmentDim: resolveToken(declarations, "--parchment-dim"),
    stone: resolveToken(declarations, "--stone"),
  };
}

describe("Currents theme tokens", () => {
  it("binds Currents backgrounds to the site palette in dark and light themes", () => {
    const dark = themeSnapshot("dark");
    const light = themeSnapshot("light");

    expect(dark.currentsBg).toBe(dark.ink);
    expect(dark.currentsBgElevated).toBe(dark.stone);
    expect(dark.currentsBorder).toBe("#3a2d12");
    expect(dark.currentsMuted).toBe(dark.parchmentDim);

    expect(light.currentsBg).toBe(light.ink);
    expect(light.currentsBgElevated).toBe(light.stone);
    expect(light.currentsBorder).toBe("#cbbfa8");
    expect(light.currentsMuted).toBe(light.parchmentDim);

    expect({ dark, light }).toMatchInlineSnapshot(`
      {
        "dark": {
          "currentsBg": "#08070a",
          "currentsBgElevated": "#08070a",
          "currentsBorder": "#3a2d12",
          "currentsMuted": "#9c8f72",
          "ink": "#08070a",
          "parchmentDim": "#9c8f72",
          "stone": "#08070a",
        },
        "light": {
          "currentsBg": "#f2e8d9",
          "currentsBgElevated": "#f2e8d9",
          "currentsBorder": "#cbbfa8",
          "currentsMuted": "#5a4e3a",
          "ink": "#f2e8d9",
          "parchmentDim": "#5a4e3a",
          "stone": "#f2e8d9",
        },
      }
    `);
  });

  it("does not leave the old grayish Currents background values in place", () => {
    const css = globalsCss();
    const oldValues = ["#141210", "#1c1916", "#2a2520", "#847c6c"];
    const currentsLines = css
      .split("\n")
      .filter((line) => line.trim().startsWith("--currents-"))
      .join("\n");

    for (const oldValue of oldValues) {
      expect(currentsLines).not.toContain(oldValue);
    }
  });
});
