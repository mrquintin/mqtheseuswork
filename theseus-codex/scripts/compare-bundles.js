#!/usr/bin/env node
/**
 * Compare two `parse-bundle-table.js` JSON outputs and enforce the
 * bundle budget.
 *
 *   node compare-bundles.js base.json head.json --ratio 1.20 --bypass false
 *
 * Exit codes:
 *   0 — every route in both files is within the budget, OR --bypass true
 *   1 — at least one route exceeded the budget and the bypass label
 *       isn't set
 *
 * Output (stdout) is a markdown table suitable for piping into
 * `$GITHUB_STEP_SUMMARY`. Keeping the formatting in one place lets the
 * CI summary and a local invocation produce identical output, which
 * matters for "why did my PR fail" reproducibility.
 */

const fs = require("node:fs");

function parseArgs(argv) {
  const args = { positional: [], ratio: 1.2, bypass: false };
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    if (flag === "--ratio") {
      args.ratio = Number(argv[++i]);
    } else if (flag === "--bypass") {
      args.bypass = String(argv[++i]).toLowerCase() === "true";
    } else {
      args.positional.push(flag);
    }
  }
  if (args.positional.length !== 2) {
    process.stderr.write(
      "usage: compare-bundles.js <base.json> <head.json> [--ratio N] [--bypass BOOL]\n",
    );
    process.exit(2);
  }
  return args;
}

function readJson(path) {
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function fmt(kb) {
  return `${kb.toFixed(1)} kB`;
}

function main() {
  const { positional, ratio, bypass } = parseArgs(process.argv.slice(2));
  const [basePath, headPath] = positional;
  const base = readJson(basePath);
  const head = readJson(headPath);

  const rows = [];
  const violations = [];
  const novel = [];

  for (const route of Object.keys(head).sort()) {
    const headKb = head[route];
    const baseKb = base[route];
    if (baseKb == null) {
      novel.push({ route, headKb });
      continue;
    }
    const change = baseKb === 0 ? 0 : (headKb - baseKb) / baseKb;
    const overBudget = headKb > baseKb * ratio;
    rows.push({ route, baseKb, headKb, change, overBudget });
    if (overBudget) violations.push({ route, baseKb, headKb, change });
  }

  // Markdown summary
  process.stdout.write(`## Bundle budget (ratio: ${ratio.toFixed(2)}×)\n\n`);
  if (rows.length > 0) {
    process.stdout.write("| Route | Base | Head | Δ |\n");
    process.stdout.write("| --- | --- | --- | --- |\n");
    for (const r of rows) {
      const pct = `${(r.change * 100).toFixed(1)}%`;
      const marker = r.overBudget ? " ⛔" : "";
      process.stdout.write(
        `| \`${r.route}\` | ${fmt(r.baseKb)} | ${fmt(r.headKb)} | ${pct}${marker} |\n`,
      );
    }
  }

  if (novel.length > 0) {
    process.stdout.write("\n### New routes (no baseline; exempt)\n\n");
    for (const n of novel) {
      process.stdout.write(`- \`${n.route}\` — ${fmt(n.headKb)}\n`);
    }
  }

  if (violations.length === 0) {
    process.stdout.write("\n✅ All routes within budget.\n");
    process.exit(0);
  }

  process.stdout.write(`\n❌ ${violations.length} route(s) exceeded the budget:\n`);
  for (const v of violations) {
    process.stdout.write(
      `  - \`${v.route}\`: ${fmt(v.baseKb)} → ${fmt(v.headKb)} (+${(v.change * 100).toFixed(1)}%)\n`,
    );
  }
  if (bypass) {
    process.stdout.write(
      "\n⚠️ `bundle-budget-bypass` label set; failing-check downgraded to warning.\n",
    );
    process.exit(0);
  }
  process.exit(1);
}

if (require.main === module) main();
