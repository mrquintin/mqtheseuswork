/**
 * Async processing: run Noosphere Typer CLI (`python -m noosphere ingest` + `synthesize`),
 * streaming stdout/stderr into Upload.processLog.
 */

import { spawn } from "child_process";
import { readFile } from "fs/promises";
import { join } from "path";
import { db } from "./db";

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

function runCmd(
  args: string[],
  uploadId: string,
  envExtra: Record<string, string>,
): Promise<{ code: number | null; out: string }> {
  return new Promise((resolve) => {
    const env = {
      ...process.env,
      ...envExtra,
      PYTHONPATH: NOOSPHERE_SRC_ROOT,
      PYTHONUNBUFFERED: "1",
    };
    const proc = spawn(NOOSPHERE_PYTHON, args, {
      env,
      cwd: join(process.cwd(), ".."),
    });
    let out = "";
    const onData = async (d: Buffer) => {
      const s = d.toString();
      out += s;
      await appendLog(uploadId, s).catch(() => {});
    };
    proc.stdout.on("data", (d) => {
      void onData(d);
    });
    proc.stderr.on("data", (d) => {
      void onData(d);
    });
    proc.on("close", (code) => resolve({ code, out }));
    proc.on("error", async (err) => {
      await appendLog(uploadId, `\n[spawn error] ${String(err)}\n`).catch(() => {});
      resolve({ code: 1, out });
    });
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
    return readFile(filePath, "utf-8");
  }
  return null;
}

async function transcribeAudio(filePath: string, originalName: string): Promise<string | null> {
  if (!OPENAI_API_KEY) {
    return null;
  }
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
    return typeof transcription === "string" ? transcription : (transcription as { text?: string }).text || null;
  } catch {
    return null;
  }
}

/**
 * Background job: mark processing → run CLI ingest + synthesize → update counts / status.
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

    await appendLog(uploadId, `\n$ ${NOOSPHERE_PYTHON} -m noosphere ingest ${upload.filePath}\n`);

    const ingestArgs = ["-m", "noosphere", "ingest", upload.filePath];
    const { code: ingestCode, out: ingestOut } = await runCmd(ingestArgs, uploadId, {});

    if (ingestCode !== 0) {
      await db.upload.update({
        where: { id: uploadId },
        data: {
          status: "failed",
          errorMessage: `noosphere ingest exited ${ingestCode}. See process log.`,
        },
      });
      return;
    }

    let artifactOk = false;
    try {
      const lines = ingestOut.trim().split("\n").filter(Boolean);
      const last = lines[lines.length - 1];
      if (last) {
        const j = JSON.parse(last) as { ok?: boolean };
        artifactOk = Boolean(j.ok);
      }
    } catch {
      artifactOk = ingestOut.includes('"ok": true');
    }

    await appendLog(uploadId, `\n— Ingest finished (ok=${artifactOk}) —\n`);
    await appendLog(uploadId, `\n$ ${NOOSPHERE_PYTHON} -m noosphere synthesize\n`);

    const { code: synCode, out: synOut } = await runCmd(
      ["-m", "noosphere", "synthesize"],
      uploadId,
      {},
    );

    await appendLog(uploadId, synOut || "");

    if (synCode !== 0) {
      await appendLog(uploadId, `\n[warn] synthesize exited ${synCode}\n`);
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
