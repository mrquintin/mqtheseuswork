import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { enqueueIngestJob } from "@/lib/jobQueue";
import { extractText } from "@/lib/extractText";
import { sanitizeText, sanitizeAndCap } from "@/lib/sanitizeText";
import { triggerNoosphereProcessing } from "@/lib/triggerNoosphereProcessing";
import { writeFile, mkdir } from "fs/promises";
import { join, extname } from "path";
import { v4 as uuid } from "uuid";

/**
 * Multipart upload handler.
 *
 * On Vercel (serverless) we can't rely on the filesystem — any writes to
 * `process.cwd()/uploads` disappear the instant the request returns.
 * Instead, this route extracts whatever textual content it can from the
 * uploaded file (plain text, PDF body, DOCX paragraphs, Whisper
 * transcript of audio) and persists it directly into `Upload.textContent`.
 * That makes the row immediately usable by `noosphere ingest-from-codex`
 * — no file retrieval needed.
 *
 * Supported types out of the box (all extracted → textContent):
 *   .txt .md .markdown .vtt .jsonl   (UTF-8 pass-through)
 *   .pdf                              (via pdf-parse)
 *   .docx                             (via mammoth)
 *   .mp3 .m4a .wav .webm .ogg         (via OpenAI Whisper; needs API key)
 *
 * For self-hosted deploys (UPLOAD_STORAGE unset), we also write the
 * original binary to `UPLOAD_LOCAL_DIR` so the Noosphere CLI running
 * locally can fall back to the raw file if extraction produced nothing.
 */

const UPLOAD_DIR =
  process.env.UPLOAD_LOCAL_DIR || join(process.cwd(), "uploads");
const DISABLE_LOCAL_WRITES =
  process.env.VERCEL === "1" || process.env.UPLOAD_STORAGE === "remote";

// Vercel Hobby: 4.5 MB request body cap. We leave 100 KB headroom for
// form fields (title, description, etc.) so the raw file can be
// ~4.4 MB. Self-hosted deploys aren't subject to this — `writeFile`
// can handle arbitrary sizes — but enforcing it everywhere keeps the
// server-vs-serverless behaviour predictable and makes local testing
// catch the eventual Vercel failure earlier.
const MAX_FILE_BYTES = Math.floor(4.4 * 1024 * 1024);

const ALLOWED_EXT = new Set([
  ".md",
  ".markdown",
  ".txt",
  ".vtt",
  ".jsonl",
  // Dialectic posts its per-session reflection bundle as a single JSON blob
  // (`{session_id}_reflection.json`). Accept it so the interlocutor record
  // round-trips into the Codex without extra rewriting on the desktop side.
  ".json",
  ".pdf",
  ".docx",
  ".mp3",
  ".m4a",
  ".wav",
  ".webm",
  ".ogg",
]);

export async function POST(req: Request) {
  try {
    // Accept either a browser cookie session or a `Authorization: Bearer tcx_…`
    // API key so Dialectic (and any CLI/automation) can upload without a UI.
    const founder = await getFounderFromAuth(req);
    if (!founder) {
      return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }

    const formData = await req.formData();
    const file = formData.get("file") as File | null;
    const title = (formData.get("title") as string) || "";
    const description = (formData.get("description") as string) || "";
    const sourceType = (formData.get("sourceType") as string) || "written";

    if (!file) {
      return NextResponse.json({ error: "No file provided" }, { status: 400 });
    }

    const ext = extname(file.name).toLowerCase();
    if (!ALLOWED_EXT.has(ext)) {
      return NextResponse.json(
        {
          error:
            `Unsupported file type ${ext || "(none)"}. Allowed: ` +
            [...ALLOWED_EXT].join(", "),
        },
        { status: 400 },
      );
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    if (buffer.length > MAX_FILE_BYTES) {
      return NextResponse.json(
        {
          error:
            `File is ${(buffer.length / 1024 / 1024).toFixed(1)} MB; the serverless ` +
            `upload limit is ${(MAX_FILE_BYTES / 1024 / 1024).toFixed(1)} MB. ` +
            "For larger files, upload from a local Noosphere CLI — or wait for " +
            "the Supabase Storage direct-upload flow.",
        },
        { status: 413 },
      );
    }

    const mime = file.type || "";

    // ── Extract text/transcript from the file ───────────────────────────
    // This happens BEFORE the Upload row is created, so `textContent` is
    // populated on insert and Noosphere can process the row immediately.
    // `extractText` never throws — it returns a structured result with
    // `textContent` (possibly null), a `note`, and a `hardFailed` flag.
    const extraction = await extractText(buffer, file.name, mime);

    // ── Persist raw bytes (self-hosted only) ────────────────────────────
    // On Vercel we lose the binary the moment the request returns, so we
    // deliberately don't write it; `filePath` is a synthetic `inline:` id.
    let filePath: string;
    if (!DISABLE_LOCAL_WRITES) {
      await mkdir(UPLOAD_DIR, { recursive: true });
      const storedName = `${uuid()}${ext || ".bin"}`;
      filePath = join(UPLOAD_DIR, storedName);
      await writeFile(filePath, buffer);
    } else {
      filePath = `inline:${uuid()}${ext}`;
    }

    // ── Create the Upload row ───────────────────────────────────────────
    // Every string headed for Postgres is sanitized here for two
    // reasons:
    //   1. Postgres rejects UTF-8 NUL bytes ("invalid byte sequence
    //      for encoding "UTF8": 0x00") — PDFs and DOCX extraction
    //      leak these. `extractText` already strips them, but we
    //      scrub again on the boundary so a future caller that
    //      bypasses `extractText` (e.g. a direct API client) can't
    //      poison the DB.
    //   2. Titles/descriptions/filenames are user-controlled, so
    //      strip C0 control chars that have no business in a label.
    const safeTitle = sanitizeText(
      title || file.name.replace(/\.[^/.]+$/, ""),
    ).slice(0, 500);
    const safeDescription = sanitizeAndCap(description, 10_000);
    const safeOriginalName = sanitizeText(file.name).slice(0, 500);
    const safeMime = sanitizeText(mime || "application/octet-stream").slice(0, 255);
    const initialLog = sanitizeAndCap(
      `— Upload received (${buffer.length.toLocaleString()} bytes) —\n` +
        `— Extraction: ${extraction.note} —\n`,
      8_000,
    );

    const upload = await db.upload.create({
      data: {
        organizationId: founder.organizationId,
        founderId: founder.id,
        title: safeTitle,
        description: safeDescription,
        sourceType: sanitizeText(sourceType).slice(0, 64) || "written",
        originalName: safeOriginalName,
        mimeType: safeMime,
        filePath,
        fileSize: buffer.length,
        textContent: extraction.textContent,
        status: "pending",
        processLog: initialLog,
        errorMessage: extraction.hardFailed
          ? sanitizeAndCap(extraction.note, 2_000)
          : null,
      },
    });

    await db.auditEvent.create({
      data: {
        organizationId: founder.organizationId,
        founderId: founder.id,
        uploadId: upload.id,
        action: "upload",
        detail: sanitizeAndCap(
          `Uploaded ${file.name} (${(buffer.length / 1024).toFixed(0)} KB) · ${extraction.mode}`,
          2_000,
        ),
      },
    });

    // Serialize the two async side-effects to avoid a race that was
    // clobbering the dispatch note. Order:
    //   1. Fire the GitHub Actions dispatch (fast, ~200ms HTTP POST).
    //   2. Wait for the response, append its status to processLog.
    //   3. THEN kick off `enqueueIngestJob` (slow on Vercel — does
    //      extraction fallback + appends its own notes).
    // Because step 3 reads-then-writes via `appendLog`, previous notes
    // are preserved. Previously both steps raced to overwrite the
    // field and the dispatch note was usually lost.
    const dispatchPromise = (async () => {
      try {
        const result = await triggerNoosphereProcessing(upload.id, {
          organizationId: founder.organizationId,
          withLlm: true,
        });
        const suffix = `\n— Auto-process: ${result.note} —\n`;
        try {
          await db.upload.update({
            where: { id: upload.id },
            data: {
              // Append the dispatch note to the existing processLog so
              // a later ingest-job write doesn't wipe it. (jobQueue's
              // `appendLog` is also read-then-write so subsequent lines
              // will preserve this too.)
              processLog: {
                set: sanitizeAndCap(initialLog + suffix, 8_000),
              },
              status: result.dispatched ? "processing" : upload.status,
            },
          });
        } catch {
          /* non-fatal */
        }
      } finally {
        // Always run the fallback ingest job. On Vercel it detects the
        // lack of Python and, if auto-processing is configured, writes
        // a short "handed off to GitHub Actions" note; if not, it
        // writes the full "run locally" instructions. Either way it
        // appends to the existing processLog instead of overwriting.
        try {
          await enqueueIngestJob(upload.id);
        } catch (err) {
          console.error(
            `Background ingestion for upload ${upload.id} failed:`,
            err,
          );
        }
      }
    })();
    // Non-blocking from the HTTP response's perspective — the user gets
    // their upload ack immediately. The dispatch + jobQueue work
    // continues after response close on Vercel's serverless runtime.
    void dispatchPromise;

    return NextResponse.json({
      id: upload.id,
      status: upload.status,
      title: upload.title,
      fileSize: upload.fileSize,
      extractionMode: extraction.mode,
      textContentChars: extraction.textContent?.length ?? 0,
      note: extraction.note,
      autoProcessing: true,
    });
  } catch (error) {
    console.error("Upload error:", error);
    return NextResponse.json(
      {
        error:
          `Upload failed: ${error instanceof Error ? error.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}
