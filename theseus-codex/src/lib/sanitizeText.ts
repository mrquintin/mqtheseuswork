/**
 * Scrub a string so it can safely be written to a Postgres UTF-8 text
 * column.
 *
 * Why this exists
 * ---------------
 * Postgres (and every other RDBMS on UTF-8) rejects strings that
 * contain the NUL character (`\u0000` / 0x00) with the error:
 *
 *   invalid byte sequence for encoding "UTF8": 0x00
 *
 * PDFs in particular leak NUL bytes everywhere — `pdf-parse` produces
 * them from binary formatting, embedded fonts, etc. DOCX extraction
 * occasionally produces them too. Whisper's verbatim transcripts can
 * contain them for silence tokens.
 *
 * In addition to NUL, other C0 control characters (0x01–0x08, 0x0B,
 * 0x0C, 0x0E–0x1F) are technically legal UTF-8 but never appear in
 * human-readable text. Keeping them around corrupts search and
 * embedding indexes without adding information. We strip those too,
 * keeping tab (0x09), newline (0x0A), and carriage return (0x0D)
 * which are routine.
 *
 * Additionally we scrub lone surrogate halves and the BOM, which
 * sometimes sneak in from Windows-encoded inputs.
 *
 * This function is idempotent and cheap (single regex pass). It
 * preserves all other content verbatim — no normalization, no case
 * changes, no collapsing.
 */

/**
 * All C0 control characters we want to drop, plus the BOM. Keep \t
 * (\x09), \n (\x0A), \r (\x0D) — everything else in 0x00..0x1F gets
 * nuked.
 */
// eslint-disable-next-line no-control-regex
const UNSAFE_CTRL = /[\x00-\x08\x0B\x0C\x0E-\x1F\uFEFF]/g;

/**
 * Lone surrogate halves — valid UTF-16 code units that aren't
 * valid UTF-8 when encoded in isolation, which makes them a source
 * of subtle Postgres errors on some server collations.
 *
 * We match ONLY unpaired halves, so genuine astral-plane characters
 * (e.g. emoji like 👋, which is U+1F44B encoded as the surrogate pair
 * `\uD83D\uDC4B`) survive the scrub. The two regexes below:
 *
 *   LONE_HIGH  — a high surrogate (D800-DBFF) NOT followed by a low
 *                surrogate (DC00-DFFF).
 *   LONE_LOW   — a low surrogate NOT preceded by a high surrogate.
 */
const LONE_HIGH = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])/g;
// eslint-disable-next-line no-misleading-character-class
const LONE_LOW = /(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g;

export function stripNullBytes(input: string): string {
  if (!input) return input;
  return input.replace(/\u0000/g, "");
}

export function sanitizeText(input: string | null | undefined): string {
  if (!input) return "";
  return input
    .replace(UNSAFE_CTRL, "")
    .replace(LONE_HIGH, "")
    .replace(LONE_LOW, "");
}

/**
 * Same as `sanitizeText` but also caps the length so a runaway PDF
 * extraction (some forms produce 30+ MB of text that's 90% garbage)
 * doesn't blow the Postgres insert or dominate LLM context budgets.
 *
 * Default cap: 2,000,000 chars (~2 MB in UTF-8 for Latin text).
 * The ingest pipeline chunks at much smaller sizes anyway; anything
 * past this cap is almost certainly not useful signal.
 */
export function sanitizeAndCap(
  input: string | null | undefined,
  maxChars = 2_000_000,
): string {
  const clean = sanitizeText(input);
  if (clean.length <= maxChars) return clean;
  return clean.slice(0, maxChars);
}

/**
 * Scrub any object shape that may end up in a Prisma text column.
 * Recursively walks strings only — objects / arrays are traversed,
 * numbers / booleans / null pass through. Useful for LLM outputs
 * that we haven't individually validated.
 */
export function sanitizeDeep<T>(value: T): T {
  if (value == null) return value;
  if (typeof value === "string") return sanitizeText(value) as unknown as T;
  if (Array.isArray(value)) {
    return value.map((v) => sanitizeDeep(v)) as unknown as T;
  }
  if (typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = sanitizeDeep(v);
    }
    return out as unknown as T;
  }
  return value;
}
