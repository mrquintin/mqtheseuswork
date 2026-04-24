/**
 * Minimal type declaration for `pdf-parse/lib/pdf-parse.js`.
 *
 * Upstream pdf-parse ships no `.d.ts` at all (neither on the top-level
 * export nor on this internal submodule). We import the submodule
 * directly because the top-level `require("pdf-parse")` runs an
 * internal self-test on load that tries to read a PDF file that isn't
 * bundled in the npm package — which breaks in production. See
 * `src/lib/extractText.ts` for the narrative.
 *
 * The shape here only covers what we actually use. `pdf-parse` also
 * populates `numpages`, `numrender`, `info`, `metadata`, `version`,
 * but we only care about the extracted text.
 */
declare module "pdf-parse/lib/pdf-parse.js" {
  export interface PdfParseResult {
    text?: string;
    numpages?: number;
  }
  const pdfParse: (buffer: Buffer | Uint8Array) => Promise<PdfParseResult>;
  export default pdfParse;
}
