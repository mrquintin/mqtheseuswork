/**
 * Server-side text/audio extraction for the upload pipeline.
 *
 * Responsibility: given an in-memory `Buffer` of an uploaded file, pull
 * whatever textual content we can out of it — plain text, PDF body,
 * DOCX paragraphs, or a Whisper transcription of audio — and return it
 * so the `/api/upload` route can persist it as `Upload.textContent` on
 * insert. That lets Noosphere (via `ingest-from-codex`) process the
 * upload without ever needing to read the original binary — which is
 * critical on Vercel's ephemeral serverless filesystem where the
 * binary is lost the moment the request finishes.
 *
 * File-type matrix
 * ----------------
 *   ext / mime       extractor           notes
 *   ────────────────────────────────────────────────────────────────
 *   .txt  .md  .vtt  buffer.toString     cheapest path
 *   .jsonl           buffer.toString     (treated as text)
 *   .pdf             pdf-parse           text-based PDFs only;
 *                                        scanned PDFs need OCR
 *                                        (not handled here)
 *   .docx            mammoth             extracts raw paragraph text
 *   .mp3 .wav .m4a   OpenAI Whisper      requires OPENAI_API_KEY
 *   .ogg .webm       OpenAI Whisper      requires OPENAI_API_KEY
 *
 * We intentionally DO NOT fail the upload if extraction fails — the
 * raw Upload row is still useful (metadata, audit trail, filePath),
 * and a later local `noosphere ingest-from-codex` can retry with more
 * powerful tools. Instead we return a structured result that the
 * caller writes into `processLog` / `errorMessage` so the user can see
 * *why* no text came out.
 */

import type { Buffer as NodeBuffer } from "node:buffer";
import { sanitizeAndCap } from "./sanitizeText";

export interface ExtractionResult {
  /** The extracted text; null if nothing could be pulled out. */
  textContent: string | null;
  /** Short human-readable note about what happened. Always non-null. */
  note: string;
  /**
   * True if the request should be treated as a failure (e.g. "file
   * obviously corrupt") vs just "no text extracted". Currently we
   * treat almost everything as non-fatal — the Upload row gets saved
   * either way; this flag just controls whether we set
   * `Upload.errorMessage`.
   */
  hardFailed: boolean;
  /** What path did we take? Useful in process-log annotation. */
  mode: "text" | "pdf" | "docx" | "whisper" | "whisper-skipped" | "unknown";
}

// `.json` is included so Dialectic's per-session reflection bundle
// (`{session_id}_reflection.json`) round-trips as textContent — it's a
// structured record of interventions/decisions, useful as audit context
// even if it won't yield standalone claims.
const TEXT_EXTS = new Set([".txt", ".md", ".markdown", ".vtt", ".jsonl", ".json"]);
const AUDIO_EXTS = new Set([".mp3", ".m4a", ".wav", ".webm", ".ogg"]);

function lowerExt(filename: string): string {
  const i = filename.lastIndexOf(".");
  return i >= 0 ? filename.slice(i).toLowerCase() : "";
}

/**
 * Trim whitespace but preserve internal newlines, then scrub NUL bytes
 * and other C0 control characters that Postgres rejects on UTF-8
 * inserts (`invalid byte sequence for encoding "UTF8": 0x00`). PDFs
 * and DOCX extraction routinely leak these, and they were silently
 * killing the upload at the Prisma insert step.
 *
 * Also caps length to 2 MB of chars so a pathological PDF can't
 * blow the insert with tens of megabytes of formatting noise.
 * Empty string after sanitization → null.
 */
function normalize(text: string | null | undefined): string | null {
  if (!text) return null;
  const cleaned = sanitizeAndCap(text).trim();
  if (!cleaned) return null;
  return cleaned;
}

export async function extractText(
  buffer: NodeBuffer,
  filename: string,
  mimeType: string,
): Promise<ExtractionResult> {
  const ext = lowerExt(filename);
  const mime = (mimeType || "").toLowerCase();

  // ── Plain text / Markdown / VTT / JSONL ─────────────────────────────
  if (
    mime.startsWith("text/") ||
    mime === "application/x-ndjson" ||
    TEXT_EXTS.has(ext)
  ) {
    const text = buffer.toString("utf-8");
    const normalized = normalize(text);
    return {
      textContent: normalized,
      note: normalized
        ? `extracted ${normalized.length.toLocaleString()} chars of plain text`
        : "file had no readable text content",
      hardFailed: false,
      mode: "text",
    };
  }

  // ── PDF ─────────────────────────────────────────────────────────────
  // We require pdf-parse's submodule directly; top-level `require("pdf-parse")`
  // runs an internal "quick test" on first load that looks for a sample
  // PDF that isn't shipped in the npm package — in production that
  // triggers an ENOENT at bundle time. Importing the inner module
  // avoids that entirely.
  if (ext === ".pdf" || mime === "application/pdf") {
    try {
      const { default: pdfParse } = await import("pdf-parse/lib/pdf-parse.js");
      const result = await pdfParse(buffer);
      const normalized = normalize(result.text);
      if (!normalized) {
        return {
          textContent: null,
          note:
            "PDF parsed but no extractable text — likely a scanned/image " +
            "PDF. Run OCR locally (e.g. `ocrmypdf`) and re-upload the " +
            "searchable version, or run noosphere ingest-from-codex " +
            "with a local OCR pipeline.",
          hardFailed: false,
          mode: "pdf",
        };
      }
      return {
        textContent: normalized,
        note: `extracted ${normalized.length.toLocaleString()} chars from PDF`,
        hardFailed: false,
        mode: "pdf",
      };
    } catch (err) {
      return {
        textContent: null,
        note: `PDF parse failed: ${err instanceof Error ? err.message : String(err)}`,
        hardFailed: true,
        mode: "pdf",
      };
    }
  }

  // ── DOCX ────────────────────────────────────────────────────────────
  if (
    ext === ".docx" ||
    mime === "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  ) {
    try {
      const mammoth = await import("mammoth");
      // `extractRawText` returns paragraph text with `\n` separators,
      // which is what we want; mammoth.convertToHtml would give us
      // <p>-tagged content that we'd have to strip anyway.
      const { value } = await mammoth.extractRawText({ buffer });
      const normalized = normalize(value);
      return {
        textContent: normalized,
        note: normalized
          ? `extracted ${normalized.length.toLocaleString()} chars from DOCX`
          : "DOCX had no extractable text",
        hardFailed: false,
        mode: "docx",
      };
    } catch (err) {
      return {
        textContent: null,
        note: `DOCX parse failed: ${err instanceof Error ? err.message : String(err)}`,
        hardFailed: true,
        mode: "docx",
      };
    }
  }

  // ── Audio (OpenAI Whisper) ──────────────────────────────────────────
  const isAudio = mime.startsWith("audio/") || AUDIO_EXTS.has(ext);
  if (isAudio) {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      return {
        textContent: null,
        note:
          "Audio saved; automatic transcription requires OPENAI_API_KEY " +
          "on the Vercel project. Set it in Vercel Settings → Environment " +
          "Variables, redeploy, and re-upload — or run " +
          "`noosphere ingest-from-codex --upload-id <id> --with-llm` " +
          "locally to transcribe after the fact.",
        hardFailed: false,
        mode: "whisper-skipped",
      };
    }
    // Whisper's file-size hard limit is 25 MB. Vercel serverless body
    // limit is 4.5 MB, which we check earlier in the route — so if we
    // got here with a buffer, it's already within Whisper's budget.
    try {
      const { default: OpenAI } = await import("openai");
      const openai = new OpenAI({ apiKey });
      // The SDK accepts a Web File; construct one from the buffer so
      // we don't need to write the audio to disk first. Node's Buffer
      // is a `Uint8Array<ArrayBufferLike>` — that union type includes
      // SharedArrayBuffer which TS-strict rejects for the File
      // constructor. We copy the bytes into a fresh typed array
      // explicitly backed by a plain `ArrayBuffer` so the constructor
      // accepts it in strict mode.
      const plainBuffer = new ArrayBuffer(buffer.byteLength);
      const bytes = new Uint8Array(plainBuffer);
      bytes.set(buffer);
      const audioFile = new File([bytes], filename, {
        type: mime || "audio/mpeg",
      });
      const result = await openai.audio.transcriptions.create({
        model: "whisper-1",
        file: audioFile,
        response_format: "text",
      });
      const transcript =
        typeof result === "string"
          ? result
          : (result as { text?: string }).text ?? null;
      const normalized = normalize(transcript);
      if (!normalized) {
        return {
          textContent: null,
          note:
            "Whisper returned an empty transcript (silent or very short audio?).",
          hardFailed: false,
          mode: "whisper",
        };
      }
      return {
        textContent: normalized,
        note:
          `transcribed ${normalized.length.toLocaleString()} chars from audio ` +
          `via OpenAI Whisper (${mime || ext})`,
        hardFailed: false,
        mode: "whisper",
      };
    } catch (err) {
      // Don't fail the upload — the row is still useful. But flag the
      // error so the user knows transcription didn't run.
      return {
        textContent: null,
        note: `Whisper transcription failed: ${err instanceof Error ? err.message : String(err)}`,
        hardFailed: true,
        mode: "whisper",
      };
    }
  }

  // ── Fallback: unknown type, no extraction available ─────────────────
  return {
    textContent: null,
    note:
      `file type ${ext || "(unknown)"} / mime ${mime || "(unknown)"} ` +
      `has no server-side extractor. Upload saved; process locally.`,
    hardFailed: false,
    mode: "unknown",
  };
}
