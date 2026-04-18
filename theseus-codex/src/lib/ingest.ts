/**
 * Background processing for uploaded files.
 *
 * Happy path (local / self-hosted): run Noosphere's Typer CLI
 * (`python -m noosphere ingest` + `synthesize`), streaming stdout/stderr
 * into `Upload.processLog` so the UI can show live progress.
 *
 * Serverless path (Vercel): Python isn't available. Previously this code
 * just `spawn`'d `python3` and the user saw `Error: spawn python3 ENOENT`
 * in the process log (see {@link NOOSPHERE_UNAVAILABLE_MESSAGE}). Now we
 * detect that case up front, mark the upload as `queued_offline` with an
 * explanatory log, and let the user run the CLI locally against the shared
 * Postgres to finish the job.
 */

import { readFile } from "fs/promises";
import { join } from "path";
import { db } from "./db";
import {
  runNoospherePython,
  isNoosphereLikelyUnavailable,
  NOOSPHERE_UNAVAILABLE_MESSAGE,
} from "./pythonRuntime";

const NOOSPHERE_PYTHON = process.env.NOOSPHERE_PYTHON || "python3";
/** Directory containing the `noosphere` Python package (parent of `noosphere/`). */
const NOOSPHERE_SRC_ROOT =
  process.env.NOOSPHERE_SRC_ROOT || join(process.cwd(), "..", "noosphere");
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";

async function appendLog(uploadId: string, chunk: string) {
  const prev = await db.upload.findUnique({
    where: { id: uploadId },
    select: { processLog: true },
  });
  const next = (prev?.processLog || "") + chunk;
  await db.upload.update({
    where: { id: uploadId },
    data: { processLog: next.slice(-200_000) },
  });
}

async function extractText(filePath: string, mimeType: string, originalName: string): Promise<string | null> {
  if (
    mimeType === "text/plain" ||
    mimeType === "text/markdown" ||
    mimeType === "text/vtt" ||
    mimeType === "application/x-ndjson" ||
    originalName.match(/\.(txt|md|markdown|vtt|jsonl)$/i)
  ) {
    // `filePath` may be a real path (self-hosted) or a marker like
    // `inline:uuid.txt` (Vercel — see api/upload/route.ts). Only read from
    // disk when it looks like an actual path.
    if (filePath.startsWith("inline:")) return null;
    return readFile(filePath, "utf-8");
  }
  return null;
}

async function transcribeAudio(filePath: string, originalName: string): Promise<string | null> {
  if (!OPENAI_API_KEY) return null;
  if (filePath.startsWith("inline:")) return null;
  try {
    const { default: OpenAI } = await import("openai");
    const openai = new OpenAI({ apiKey: OPENAI_API_KEY });
    const fileBuffer = await readFile(filePath);
    const file = new File([fileBuffer], originalName, { type: "audio/mpeg" });
    const transcription = await openai.audio.transcriptions.create({
      model: "whisper-1",
      file,
      response_format: "text",
    });
    return typeof transcription === "string"
      ? transcription
      : (transcription as { text?: string }).text || null;
  } catch {
    return null;
  }
}

/**
 * Background job: mark processing → (try to) run CLI ingest + synthesize
 * → update counts / status. When Python isn't reachable we still persist
 * textContent to Postgres and set status to `queued_offline` so the user
 * can find the upload in the UI and run the CLI locally.
 */
export async function processUpload(uploadId: string): Promise<void> {
  const upload = await db.upload.findUnique({
    where: { id: uploadId },
    include: { founder: true },
  });

  if (!upload) {
    console.error(`Upload ${uploadId} not found`);
    return;
  }

  try {
    await db.upload.update({
      where: { id: uploadId },
      data: { status: "processing", processLog: "— Starting Noosphere ingest —\n" },
    });

    let textContent = upload.textContent;
    if (!textContent) {
      const isAudio = upload.mimeType.startsWith("audio/");
      if (isAudio) {
        textContent = await transcribeAudio(upload.filePath, upload.originalName);
      } else {
        textContent = await extractText(upload.filePath, upload.mimeType, upload.originalName);
      }
      if (textContent) {
        await db.upload.update({ where: { id: uploadId }, data: { textContent } });
      }
    }

    // ────────────────────────────────────────────────────────────────────
    // Serverless / Python-less hosts: don't even try to spawn. The upload
    // row is already persisted (textContent is in Postgres for text-like
    // files), so mark it as queued for offline processing and return.
    // ────────────────────────────────────────────────────────────────────
    if (isNoosphereLikelyUnavailable()) {
      await appendLog(
        uploadId,
        `\n${NOOSPHERE_UNAVAILABLE_MESSAGE}\n\n` +
          `To process this upload, on a machine with Noosphere installed run:\n\n` +
          `    # One-time: point Noosphere at the shared Supabase DB\n` +
          `    export DIRECT_URL="postgresql://postgres.<ref>:<pw>@aws-<n>-<region>.pooler.supabase.com:5432/postgres"\n\n` +
          `    # Extract claims from this specific upload (naive splitter; no LLM required)\n` +
          `    python -m noosphere ingest-from-codex --upload-id ${uploadId}\n\n` +
          `    # Or: list everything that's still queued\n` +
          `    python -m noosphere codex-queued\n\n` +
          `Add --with-llm for higher-quality claim extraction ` +
          `(requires ANTHROPIC_API_KEY or OPENAI_API_KEY).\n`,
      );
      await db.upload.update({
        where: { id: uploadId },
        data: {
          status: "queued_offline",
          errorMessage: null,
        },
      });
      await db.auditEvent.create({
        data: {
          organizationId: upload.organizationId,
          founderId: upload.founderId,
          uploadId: upload.id,
          action: "queued_offline",
          detail:
            "Upload stored; Noosphere CLI unavailable in this runtime. " +
            "Process locally to materialise claims/conclusions.",
        },
      });
      return;
    }

    await appendLog(uploadId, `\n$ ${NOOSPHERE_PYTHON} -m noosphere ingest ${upload.filePath}\n`);

    const ingestArgs = ["-m", "noosphere", "ingest", upload.filePath];
    const ingest = await runNoospherePython(ingestArgs, {
      cwd: join(process.cwd(), ".."),
      envExtra: { PYTHONPATH: NOOSPHERE_SRC_ROOT },
      onChunk: (s) => appendLog(uploadId, s),
    });

    // Belt-and-suspenders: even though we checked up front, a
    // misconfigured host could still surprise us with ENOENT. Handle it.
    if (ingest.skipped) {
      await appendLog(
        uploadId,
        `\n${NOOSPHERE_UNAVAILABLE_MESSAGE}\n` +
          `(Detected at spawn time. Marking upload as queued for offline ingest.)\n`,
      );
      await db.upload.update({
        where: { id: uploadId },
        data: { status: "queued_offline" },
      });
      return;
    }

    if (ingest.code !== 0) {
      await db.upload.update({
        where: { id: uploadId },
        data: {
          status: "failed",
          errorMessage: `noosphere ingest exited ${ingest.code}. See process log.`,
        },
      });
      return;
    }

    let artifactOk = false;
    try {
      const lines = ingest.out.trim().split("\n").filter(Boolean);
      const last = lines[lines.length - 1];
      if (last) {
        const j = JSON.parse(last) as { ok?: boolean };
        artifactOk = Boolean(j.ok);
      }
    } catch {
      artifactOk = ingest.out.includes('"ok": true');
    }

    await appendLog(uploadId, `\n— Ingest finished (ok=${artifactOk}) —\n`);
    await appendLog(uploadId, `\n$ ${NOOSPHERE_PYTHON} -m noosphere synthesize\n`);

    const synth = await runNoospherePython(["-m", "noosphere", "synthesize"], {
      cwd: join(process.cwd(), ".."),
      envExtra: { PYTHONPATH: NOOSPHERE_SRC_ROOT },
      onChunk: (s) => appendLog(uploadId, s),
    });

    if (synth.skipped) {
      await appendLog(
        uploadId,
        `\n[warn] synthesize skipped — Noosphere CLI disappeared between ingest and synthesize. ` +
          `Upload is ingested but unsynthesized.\n`,
      );
    } else if (synth.code !== 0) {
      await appendLog(uploadId, `\n[warn] synthesize exited ${synth.code}\n`);
    }

    await db.upload.update({
      where: { id: uploadId },
      data: {
        status: "ingested",
        claimsCount: artifactOk ? 1 : 0,
        principleCount: 0,
        methodCount: 0,
        substCount: 0,
      },
    });

    await db.auditEvent.create({
      data: {
        organizationId: upload.organizationId,
        founderId: upload.founderId,
        uploadId: upload.id,
        action: "ingest",
        detail: "noosphere ingest + synthesize completed",
      },
    });
  } catch (err) {
    console.error(`Processing upload ${uploadId} failed:`, err);
    await db.upload.update({
      where: { id: uploadId },
      data: {
        status: "failed",
        errorMessage: err instanceof Error ? err.message : "Unknown error",
      },
    });
  }
}
