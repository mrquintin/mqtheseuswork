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
    forecastsBg: resolveToken(declarations, "--forecasts-bg"),
    forecastsBgElevated: resolveToken(declarations, "--forecasts-bg-elevated"),
    forecastsBorder: resolveToken(declarations, "--forecasts-border"),
    forecastsCoolGold: resolveToken(declarations, "--forecasts-cool-gold"),
    forecastsMuted: resolveToken(declarations, "--forecasts-muted"),
    forecastsParchment: resolveToken(declarations, "--forecasts-parchment"),
    ink: resolveToken(declarations, "--ink"),
    parchment: resolveToken(declarations, "--parchment"),
    parchmentDim: resolveToken(declarations, "--parchment-dim"),
    stone: resolveToken(declarations, "--stone"),
  };
}

describe("Forecasts theme tokens", () => {
  it("binds Forecasts backgrounds to the site palette in dark and light themes", () => {
    const dark = themeSnapshot("dark");
    const light = themeSnapshot("light");

    expect(dark.forecastsBg).toBe(dark.ink);
    expect(dark.forecastsBgElevated).toBe(dark.stone);
    expect(dark.forecastsBorder).toBe("#3a2d12");
    expect(dark.forecastsMuted).toBe(dark.parchmentDim);
    expect(dark.forecastsParchment).toBe(dark.parchment);
    expect(dark.forecastsCoolGold).toBe("#e9a338");

    expect(light.forecastsBg).toBe(light.ink);
    expect(light.forecastsBgElevated).toBe(light.stone);
    expect(light.forecastsBorder).toBe("#cbbfa8");
    expect(light.forecastsMuted).toBe(light.parchmentDim);
    expect(light.forecastsParchment).toBe(light.parchment);
    expect(light.forecastsCoolGold).toBe("#7a5218");

    expect({ dark, light }).toMatchInlineSnapshot(`
      {
        "dark": {
          "forecastsBg": "#08070a",
          "forecastsBgElevated": "#08070a",
          "forecastsBorder": "#3a2d12",
          "forecastsCoolGold": "#e9a338",
          "forecastsMuted": "#c3b28d",
          "forecastsParchment": "#efe2c7",
          "ink": "#08070a",
          "parchment": "#efe2c7",
          "parchmentDim": "#c3b28d",
          "stone": "#08070a",
        },
        "light": {
          "forecastsBg": "#f2e8d9",
          "forecastsBgElevated": "#f2e8d9",
          "forecastsBorder": "#cbbfa8",
          "forecastsCoolGold": "#7a5218",
          "forecastsMuted": "#5a4e3a",
          "forecastsParchment": "#2a2318",
          "ink": "#f2e8d9",
          "parchment": "#2a2318",
          "parchmentDim": "#5a4e3a",
          "stone": "#f2e8d9",
        },
      }
    `);
  });

  it("does not leave the old separate Forecasts surface palette in place", () => {
    const css = globalsCss();
    const oldValues = ["#14130f", "#1c1a14", "#2a261d", "#b0a896", "#847c6c", "#c4a04b"];
    const surfaceLines = css
      .split("\n")
      .filter((line) =>
        [
          "--forecasts-bg:",
          "--forecasts-bg-elevated:",
          "--forecasts-border:",
          "--forecasts-parchment:",
          "--forecasts-parchment-dim:",
          "--forecasts-muted:",
          "--forecasts-cool-gold:",
          "--forecasts-prob-track:",
        ].some((prefix) => line.trim().startsWith(prefix)),
      )
      .join("\n");

    for (const oldValue of oldValues) {
      expect(surfaceLines).not.toContain(oldValue);
    }
  });
});
