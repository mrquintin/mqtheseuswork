import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { enqueueIngestJob } from "@/lib/jobQueue";
import { writeFile, mkdir } from "fs/promises";
import { join, extname } from "path";
import { v4 as uuid } from "uuid";

// Serverless filesystems (Vercel/Netlify) are ephemeral: writes to
// process.cwd() disappear between invocations. For cloud deploys the correct
// path is Supabase Storage via a pre-signed URL. We still write to local disk
// when UPLOAD_LOCAL_DIR is set (local Docker / Render with persistent disk).
const UPLOAD_DIR =
  process.env.UPLOAD_LOCAL_DIR || join(process.cwd(), "uploads");
const DISABLE_LOCAL_WRITES =
  process.env.VERCEL === "1" || process.env.UPLOAD_STORAGE === "remote";

const ALLOWED_EXT = new Set([
  ".md",
  ".markdown",
  ".txt",
  ".vtt",
  ".jsonl",
  ".pdf",
  ".docx",
  ".mp3",
  ".m4a",
  ".wav",
  ".webm",
  ".ogg",
]);

/**
 * Multipart upload: .md, .txt, .vtt, .jsonl (+ pdf/docx/audio), saved under /uploads (not public/).
 */
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
        { error: `Unsupported file type ${ext || "(none)"}. Allowed: ${[...ALLOWED_EXT].join(", ")}` },
        { status: 400 },
      );
    }

    const buffer = Buffer.from(await file.arrayBuffer());

    // On Vercel the filesystem is ephemeral — every invocation starts fresh,
    // so writing to `/uploads` is effectively `/dev/null`. The right path for
    // audio/PDF is Supabase Storage (pre-signed URL flow, not implemented in
    // this route yet). Text-only uploads (jsonl/txt/md/vtt) still work on
    // serverless because we persist `textContent` directly to Postgres.
    let filePath = "";
    const isTextLike =
      (file.type || "").startsWith("text/") ||
      file.type === "application/x-ndjson" ||
      [".txt", ".md", ".markdown", ".vtt", ".jsonl"].some((s) =>
        file.name.toLowerCase().endsWith(s),
      );

    if (DISABLE_LOCAL_WRITES && !isTextLike) {
      return NextResponse.json(
        {
          error:
            "Binary uploads require Supabase Storage (not yet wired up in this deployment). " +
            "Upload a .jsonl / .txt / .md / .vtt for now — those are stored inline in Postgres.",
        },
        { status: 413 },
      );
    }

    if (!DISABLE_LOCAL_WRITES) {
      await mkdir(UPLOAD_DIR, { recursive: true });
      const storedName = `${uuid()}${ext || ".bin"}`;
      filePath = join(UPLOAD_DIR, storedName);
      await writeFile(filePath, buffer);
    } else {
      filePath = `inline:${uuid()}${ext}`;
    }

    let textContent: string | null = null;
    const mime = file.type || "";

    if (isTextLike) {
      textContent = buffer.toString("utf-8");
    }

    const upload = await db.upload.create({
      data: {
        organizationId: founder.organizationId,
        founderId: founder.id,
        title: title || file.name.replace(/\.[^/.]+$/, ""),
        description,
        sourceType,
        originalName: file.name,
        mimeType: mime || "application/octet-stream",
        filePath,
        fileSize: buffer.length,
        textContent,
        status: "pending",
        processLog: "",
      },
    });

    await db.auditEvent.create({
      data: {
        organizationId: founder.organizationId,
        founderId: founder.id,
        uploadId: upload.id,
        action: "upload",
        detail: `Uploaded ${file.name} (${(buffer.length / 1024).toFixed(0)} KB)`,
      },
    });

    enqueueIngestJob(upload.id).catch((err) => {
      console.error(`Background ingestion for upload ${upload.id} failed:`, err);
    });

    return NextResponse.json({
      id: upload.id,
      status: upload.status,
      title: upload.title,
      fileSize: upload.fileSize,
    });
  } catch (error) {
    console.error("Upload error:", error);
    return NextResponse.json({ error: "Upload failed" }, { status: 500 });
  }
}
