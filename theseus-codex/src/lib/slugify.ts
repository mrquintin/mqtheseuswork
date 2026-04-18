/**
 * Build a URL-safe slug from free-form text.
 *
 * Priorities (in order):
 *   1. Produce a recognisable slug from the title — slug should look
 *      like "how-the-firm-thinks-about-model-drift" not "post-f72a".
 *   2. Deterministic given the same input: same title yields the same
 *      slug. Uniqueness collisions are handled by the caller (which
 *      appends a numeric suffix), not here.
 *   3. Safe for `/post/:slug` routing — no characters that URL-encode
 *      to anything surprising, no leading/trailing dashes, no double
 *      dashes.
 *
 * We strip diacritics via NFKD normalization first so "Noûs" becomes
 * "nous" rather than "noxas"-style gibberish.
 */
export function slugify(input: string): string {
  if (!input) return "";
  const ascii = input
    .normalize("NFKD")
    // Remove combining diacritical marks (the "nûs" → "nus" stage).
    .replace(/[\u0300-\u036f]/g, "")
    // Collapse all non-alphanumerics to a single hyphen.
    .replace(/[^a-zA-Z0-9]+/g, "-")
    // Strip leading/trailing hyphens.
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
  // Cap at 80 chars on a word boundary so the URL stays a reasonable
  // length even for essay-length titles.
  if (ascii.length <= 80) return ascii;
  const cut = ascii.slice(0, 80);
  const lastDash = cut.lastIndexOf("-");
  return lastDash > 30 ? cut.slice(0, lastDash) : cut;
}

/**
 * Given a desired slug and an `isTaken` probe, return a slug that
 * doesn't collide. We try the plain form first, then `-2`, `-3`, …
 * up to `-99` before giving up and appending a 6-char hex suffix.
 * In practice collisions are extremely rare — founders don't title
 * two posts identically.
 */
export async function pickAvailableSlug(
  desired: string,
  isTaken: (slug: string) => Promise<boolean>,
): Promise<string> {
  const base = slugify(desired) || "post";
  if (!(await isTaken(base))) return base;
  for (let n = 2; n < 100; n++) {
    const candidate = `${base}-${n}`;
    if (!(await isTaken(candidate))) return candidate;
  }
  // Fallback — 6 hex chars of randomness beyond a `-`.
  const suffix = Math.random().toString(16).slice(2, 8);
  return `${base}-${suffix}`;
}
