/**
 * Algorithm triage queue — UI contract tests.
 *
 * The vitest profile this project uses runs under `node` (no jsdom),
 * so we cannot mount React.  Instead we verify the round-trip
 * contract for accept-with-edit by reading the QueueClient + page
 * sources and asserting that:
 *
 *   1. The accept-with-edit form posts the same field names that the
 *      page's accept server action reads from FormData.
 *   2. The server action threads those field names into
 *      `acceptAlgorithm` (the persistence helper).
 *   3. `acceptAlgorithm` writes those fields onto the Prisma row.
 *
 * Any of those three legs going out of sync would silently drop a
 * founder edit on its way to persistence — the regression this test
 * exists to catch.
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const REPO_ROOT = path.resolve(__dirname, "..");

const PAGE_PATH = path.join(
  REPO_ROOT,
  "src",
  "app",
  "(authed)",
  "algorithms",
  "queue",
  "page.tsx",
);
const CLIENT_PATH = path.join(
  REPO_ROOT,
  "src",
  "app",
  "(authed)",
  "algorithms",
  "queue",
  "QueueClient.tsx",
);
const API_PATH = path.join(REPO_ROOT, "src", "lib", "algorithmsApi.ts");

function read(p: string): string {
  expect(fs.existsSync(p), `missing source at ${p}`).toBe(true);
  return fs.readFileSync(p, "utf8");
}

describe("algorithms queue triage — accept-with-edit round-trip", () => {
  it("edit form posts the field names the server action reads", () => {
    const client = read(CLIENT_PATH);
    // Three editable fields: name, description, triggerPredicate.
    // The form is rendered inside `isEditing ? (<form ...>...</form>) : null`.
    const formMatch = client.match(
      /accept-edit-form[\s\S]+?<\/form>/,
    );
    expect(
      formMatch,
      "QueueClient must render the accept-with-edit <form> block",
    ).not.toBeNull();
    const formBlock = formMatch![0];
    expect(formBlock).toMatch(/name="id"/);
    expect(formBlock).toMatch(/name="name"/);
    expect(formBlock).toMatch(/name="description"/);
    expect(formBlock).toMatch(/name="triggerPredicate"/);
  });

  it("page accept server action reads the same FormData keys the edit form posts", () => {
    const page = read(PAGE_PATH);
    expect(page).toMatch(/async function acceptAction\(formData: FormData\)/);
    // The server action must pull `name`, `description`, and
    // `triggerPredicate` off the FormData and forward them to
    // acceptAlgorithm.
    expect(page).toMatch(/formData\.get\(\s*"id"\s*\)/);
    expect(page).toMatch(/formData\.get\(\s*"name"\s*\)/);
    expect(page).toMatch(/formData\.get\(\s*"description"\s*\)/);
    expect(page).toMatch(/formData\.get\(\s*"triggerPredicate"\s*\)/);
    expect(page).toMatch(/acceptAlgorithm\(/);
  });

  it("acceptAlgorithm threads name / description / triggerPredicate into the Prisma write", () => {
    const api = read(API_PATH);
    // Find the acceptAlgorithm function body.
    const match = api.match(
      /export async function acceptAlgorithm\([\s\S]+?\n\}/,
    );
    expect(
      match,
      "algorithmsApi must export acceptAlgorithm",
    ).not.toBeNull();
    const body = match![0];
    // The edits must flow into the Prisma update.
    expect(body).toMatch(/input\.name/);
    expect(body).toMatch(/input\.description/);
    expect(body).toMatch(/input\.triggerPredicate/);
    expect(body).toMatch(/status:\s*"ACTIVE"/);
    expect(body).toMatch(/db\.logicalAlgorithm\.updateMany/);
  });

  it("reject form posts a 'reason' field the page reads", () => {
    const client = read(CLIENT_PATH);
    const rejectBlock = client.match(/reject-form[\s\S]+?<\/form>/);
    expect(rejectBlock).not.toBeNull();
    expect(rejectBlock![0]).toMatch(/name="reason"/);

    const page = read(PAGE_PATH);
    expect(page).toMatch(/async function rejectAction\(formData: FormData\)/);
    expect(page).toMatch(/formData\.get\(\s*"reason"\s*\)/);
    expect(page).toMatch(/rejectAlgorithm\(/);
  });

  it("merge form posts intoId; page passes it to mergeAlgorithm", () => {
    const client = read(CLIENT_PATH);
    const mergeBlock = client.match(/merge-form[\s\S]+?<\/form>/);
    expect(mergeBlock).not.toBeNull();
    expect(mergeBlock![0]).toMatch(/name="intoId"/);

    const page = read(PAGE_PATH);
    expect(page).toMatch(/async function mergeAction\(formData: FormData\)/);
    expect(page).toMatch(/formData\.get\(\s*"intoId"\s*\)/);
    expect(page).toMatch(/mergeAlgorithm\(/);
  });

  it("bulk accept fires the action one row at a time, gate-checked", () => {
    const client = read(CLIENT_PATH);
    // The bulk-accept handler must loop over rows and await per row
    // so an individual row's failure surfaces immediately rather than
    // poisoning a batched call.
    expect(client).toMatch(/data-testid="bulk-accept-button"/);
    const fn = client.match(/runBulkAccept[\s\S]+?\}, \[acceptAction\]\);/);
    expect(
      fn,
      "QueueClient must define a runBulkAccept callback",
    ).not.toBeNull();
    expect(fn![0]).toMatch(/for \(const id of ids\)/);
    expect(fn![0]).toMatch(/await\s+Promise\.resolve\(acceptAction\(fd\)\)/);
  });

  it("queue page is gated by tenant context and never auto-promotes", () => {
    const page = read(PAGE_PATH);
    expect(page).toMatch(/requireTenantContext\(\)/);
    expect(page).toMatch(/listQueuedAlgorithms\(/);
    // Sanity: the page never sets ACTIVE itself — promotions only
    // flow through the per-row accept action.
    const directActive = page.match(/status:\s*"ACTIVE"/);
    expect(
      directActive,
      "page.tsx must not set status='ACTIVE' directly outside the accept helper",
    ).toBeNull();
  });
});
