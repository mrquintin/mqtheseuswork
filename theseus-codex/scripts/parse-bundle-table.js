#!/usr/bin/env node
/**
 * Parse the per-route bundle table that `next build` prints to stdout
 * and emit a JSON map of `{ route: firstLoadKB }`.
 *
 * Why this is its own script (rather than inline in the workflow):
 *   - keeps the regex + numeric coercion under unit-testable control;
 *   - lets a developer reproduce the CI bundle-budget locally with
 *     `node scripts/parse-bundle-table.js build_head.txt`;
 *   - the next.js output format has changed in ways that broke a
 *     previous in-workflow awk parser, so keeping the parser here
 *     means future Next upgrades touch one file, not the workflow yaml.
 *
 * The format we accept is the table that looks like:
 *
 *   Route (app)                              Size  First Load JS
 *   ┌ ○ /                                    268 kB         268 kB
 *   ├ ƒ /(authed)/dashboard                  412 kB         412 kB
 *   ...
 *
 * We pull the route name (column 1) and the *last* size column on the
 * row (First Load JS). Units may be `kB` or `B`; both are normalised
 * to kB. Rows whose route doesn't start with `/` (the `+ First Load JS
 * shared by all` footer) are skipped.
 */

const fs = require("node:fs");

function parseUnitToKb(value, unit) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  switch (unit.toLowerCase()) {
    case "kb":
      return num;
    case "mb":
      return num * 1024;
    case "b":
      return num / 1024;
    default:
      return null;
  }
}

function parseRow(line) {
  // The boxed table characters confuse simple splitters, so we strip
  // them first and then split on runs of two-or-more spaces (Next's
  // output is column-aligned with multi-space padding).
  const cleaned = line.replace(/^[\s┌├└│─┐┘]+/, "").trim();
  if (!cleaned.startsWith("/") && !cleaned.match(/^[○ƒλ●]\s+\//)) return null;

  // Strip a leading single-char route-type marker (○ Static, ƒ Dynamic,
  // λ Lambda, ● SSG/ISR — Next emits one of these as the first column).
  const routeStripped = cleaned.replace(/^[○ƒλ●]\s+/, "");

  // After stripping markers, split on runs of >= 2 spaces. The first
  // segment is the route, the last two segments are size + first-load.
  const segments = routeStripped.split(/\s{2,}/).filter(Boolean);
  if (segments.length < 3) return null;

  const route = segments[0].trim();
  const last = segments[segments.length - 1].trim();
  const match = last.match(/^([\d.]+)\s*(kB|MB|B)$/i);
  if (!match) return null;

  const kb = parseUnitToKb(match[1], match[2]);
  if (kb == null) return null;
  return { route, firstLoadKb: kb };
}

function main() {
  const [, , inputPath] = process.argv;
  if (!inputPath) {
    process.stderr.write("usage: parse-bundle-table.js <build-output.txt>\n");
    process.exit(2);
  }
  const text = fs.readFileSync(inputPath, "utf8");
  const out = {};
  for (const line of text.split(/\r?\n/)) {
    const row = parseRow(line);
    if (row) out[row.route] = row.firstLoadKb;
  }
  process.stdout.write(JSON.stringify(out, null, 2) + "\n");
}

if (require.main === module) main();

module.exports = { parseRow };
