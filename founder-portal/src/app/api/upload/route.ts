import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { enqueueIngestJob } from "@/lib/jobQueue";
import { writeFile, mkdir } from "fs/promises";
import { join, extname } from "path";
import { v4 as uuid } from "uuid";

const UPLOAD_DIR = join(process.cwd(), "uploads");

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
    const founder = await getFounder();
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

    await mkdir(UPLOAD_DIR, { recursive: true });

    const storedName = `${uuid()}${ext || ".bin"}`;
    const filePath = join(UPLOAD_DIR, storedName);

    const buffer = Buffer.from(await file.arrayBuffer());
    await writeFile(filePath, buffer);

    let textContent: string | null = null;
    const mime = file.type || "";

    if (
      mime.startsWith("text/") ||
      mime === "application/x-ndjson" ||
      [".txt", ".md", ".markdown", ".vtt", ".jsonl"].some((s) => file.name.toLowerCase().endsWith(s))
    ) {
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
