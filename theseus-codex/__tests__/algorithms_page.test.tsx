/**
 * Contract tests for the public `/algorithms` surface family.
 *
 * The vitest profile this project uses runs under `node` (no jsdom),
 * so we cannot mount React. Instead we read the page sources and
 * verify the load-bearing contract: each page wires the right loader,
 * each surface renders the components the spec named, and the
 * operator-only fields the spec banned never appear in the public
 * components.
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const REPO_ROOT = path.resolve(__dirname, "..");

function read(relative: string): string {
  const full = path.join(REPO_ROOT, relative);
  expect(fs.existsSync(full), `missing source at ${full}`).toBe(true);
  return fs.readFileSync(full, "utf8");
}

describe("/algorithms public index page", () => {
  const page = read("src/app/algorithms/page.tsx");

  it("renders the AlgorithmCard component for each active algorithm", () => {
    expect(page).toMatch(/import\s+AlgorithmCard\s+from/);
    expect(page).toMatch(/<AlgorithmCard\b/);
  });

  it("loads algorithms via the public-api loader", () => {
    expect(page).toMatch(/listPublicAlgorithms/);
  });

  it("exposes status / domain / sort filter controls", () => {
    expect(page).toMatch(/data-testid="filter-status"/);
    expect(page).toMatch(/data-testid="filter-sort"/);
    // The filter for source-principle pills is rendered when at least
    // one algorithm exposes a principle id, so the JSX must be present.
    expect(page).toMatch(/data-testid="filter-principle"/);
  });

  it("defaults the status filter to ACTIVE", () => {
    expect(page).toMatch(/parseStatus\(sp\.status\)/);
    expect(page).toMatch(/return "ACTIVE"/);
  });

  it("opens the lede with copy explaining what the page is for", () => {
    expect(page).toMatch(/Theseus runs/);
    expect(page).toMatch(/firm thinking in public/i);
  });
});

describe("/algorithms/[id] detail page", () => {
  const page = read("src/app/algorithms/[id]/page.tsx");

  it("renders the reasoning chain via ReasoningTraceList", () => {
    expect(page).toMatch(/import\s+ReasoningTraceList/);
    expect(page).toMatch(/<ReasoningTraceList\b/);
  });

  it("renders the trigger predicate as plain English", () => {
    expect(page).toMatch(/import\s+TriggerPredicatePlain/);
    expect(page).toMatch(/<TriggerPredicatePlain\b/);
  });

  it("renders LiveInputValuePill for each declared input", () => {
    expect(page).toMatch(/import\s+LiveInputValuePill/);
    expect(page).toMatch(/<LiveInputValuePill\b/);
  });

  it("renders the InvocationTable for the recent invocations", () => {
    expect(page).toMatch(/import\s+InvocationTable/);
    expect(page).toMatch(/<InvocationTable\b/);
  });

  it("renders the calibration spark chart", () => {
    expect(page).toMatch(/import\s+CalibrationSpark/);
    expect(page).toMatch(/<CalibrationSpark\b/);
  });

  it("renders the bet log section", () => {
    expect(page).toMatch(/data-testid="bet-log"/);
    expect(page).toMatch(/Live-money positions are operator-only/i);
  });
});

describe("/algorithms/[id]/invocations/[invocationId] drill page", () => {
  const page = read(
    "src/app/algorithms/[id]/invocations/[invocationId]/page.tsx",
  );

  it("renders observed inputs, the reasoning trace, and resolution panels", () => {
    expect(page).toMatch(/data-testid="observed-inputs"/);
    expect(page).toMatch(/<ReasoningTraceList\b/);
    expect(page).toMatch(/data-testid="resolution-panel"/);
    expect(page).toMatch(/data-testid="bet-implied"/);
    expect(page).toMatch(/data-testid="permalink"/);
  });

  it("shows UNRESOLVED rows rather than hiding them", () => {
    expect(page).toMatch(/UNRESOLVED/);
    expect(page).toMatch(/institutional dishonesty/i);
  });

  it("loads invocation drill data via the public-api loader", () => {
    expect(page).toMatch(/getInvocation/);
  });
});

describe("operator-only fields stay out of the public surface", () => {
  it("AlgorithmCard never references the runtime `_meta` block", () => {
    const card = read("src/components/algorithms/AlgorithmCard.tsx");
    expect(card).not.toMatch(/_meta/);
    expect(card).not.toMatch(/wallet/i);
    expect(card).not.toMatch(/tokens?_used/);
  });

  it("public loader strips the `_meta` block from derived outputs", () => {
    const lib = read("src/lib/algorithmsPublicApi.ts");
    expect(lib).toMatch(/stripMeta/);
    expect(lib).toMatch(/if \(k === "_meta"\) continue/);
  });
});

describe("Next.js API surfaces", () => {
  it("exposes /api/algorithms (list)", () => {
    const route = read("src/app/api/algorithms/route.ts");
    expect(route).toMatch(/export async function GET/);
    expect(route).toMatch(/listPublicAlgorithms/);
  });

  it("exposes /api/algorithms/[id] (detail)", () => {
    const route = read("src/app/api/algorithms/[id]/route.ts");
    expect(route).toMatch(/export async function GET/);
    expect(route).toMatch(/getPublicAlgorithm/);
  });

  it("exposes /api/algorithms/stream (SSE bridge)", () => {
    const route = read("src/app/api/algorithms/stream/route.ts");
    expect(route).toMatch(/text\/event-stream/);
    expect(route).toMatch(/v1\/algorithms\/stream/);
  });
});
