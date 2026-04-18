/**
 * POST /api/upload/signed/finalize/:id
 *
 * Step 2 of 2 for direct-to-storage uploads. Called by the client
 * after it has successfully PUT the file bytes to the signed URL
 * from /api/upload/signed/prepare. This endpoint:
 *
 *   1. verifies the Upload row belongs to the caller;
 *   2. HEADs the object in Supabase Storage to confirm the PUT
 *      actually landed — stops a malicious client from POSTing to
 *      /finalize without uploading anything;
 *   3. for **audio** rows, sets `Upload.audioUrl` to the public URL
 *      so /post/[slug] renders the <audio> player;
 *   4. for **text-extractable** rows (PDF / DOCX / txt / md / vtt /
 *      jsonl / json), fetches the bytes back from Storage and runs
 *      `extractText` to populate `Upload.textContent` — identical
 *      to the inline /api/upload path, just with the bytes coming
 *      from Storage instead of the request body;
 *   5. fires the Noosphere ingest dispatch so the backend pipeline
 *      (Whisper for audio; LLM claim extraction for all) runs.
 *
 * All steps are idempotent: a retry on an already-finalized row
 * returns 200 with the existing state rather than erroring.
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { extractText } from "@/lib/extractText";
import { sanitizeAndCap } from "@/lib/sanitizeText";
import {
  audioObjectExists,
  getPublicAudioUrl,
  isAudioStorageConfigured,
} from "@/lib/supabaseStorage";
import { triggerNoosphereProcessing } from "@/lib/triggerNoosphereProcessing";

const AUDIO_MIME_OR_EXT = /^(audio\/|.*\.(mp3|m4a|wav|webm|ogg|aac)$)/i;

function isAudioUpload(mimeType: string, originalName: string): boolean {
  return (
    mimeType.toLowerCase().startsWith("audio/") ||
    AUDIO_MIME_OR_EXT.test(originalName.toLowerCase())
  );
}

/**
 * Server-side download of an object we just uploaded via the signed
 * URL. Supabase serves public buckets at /object/public/<bucket>/<path>
 * without auth, so we can just fetch the public URL. For larger
 * files (50+ MB) this re-downloads inside the Vercel function, which
 * is fine for text extraction — PDFs and DOCX extract in under a
 * minute even at several hundred MB.
 *
 * Guarded by a size cap so a pathological 500 MB PDF doesn't blow
 * the Vercel function's memory — for files bigger than this, we
 * skip extraction and leave `textContent` null. The file is still
 * uploaded + available; Noosphere just has to wait for a machine
 * with enough RAM to extract it later.
 */
const TEXT_EXTRACTION_MAX_BYTES = 80 * 1024 * 1024;

async function extractFromStorage(
  publicUrl: string,
  originalName: string,
  mimeType: string,
  expectedSize: number,
): Promise<{
  textContent: string | null;
  note: string;
  hardFailed: boolean;
}> {
  if (expectedSize > TEXT_EXTRACTION_MAX_BYTES) {
    return {
      textContent: null,
      note:
        `File is ${(expectedSize / 1024 / 1024).toFixed(1)} MB — above ` +
        `the ${(TEXT_EXTRACTION_MAX_BYTES / 1024 / 1024).toFixed(0)} MB ` +
        `server-side extraction cap. Upload saved; run a local Noosphere ` +
        `ingest to extract text from the stored file.`,
      hardFailed: false,
    };
  }
  try {
    const res = await fetch(publicUrl);
    if (!res.ok) {
      return {
        textContent: null,
        note: `Couldn't fetch uploaded file back from Storage (HTTP ${res.status}).`,
        hardFailed: true,
      };
    }
    const ab = await res.arrayBuffer();
    const buffer = Buffer.from(ab);
    const result = await extractText(buffer, originalName, mimeType);
    return {
      textContent: result.textContent,
      note: result.note,
      hardFailed: result.hardFailed,
    };
  } catch (err) {
    return {
      textContent: null,
      note: `Storage fetch failed: ${err instanceof Error ? err.message : String(err)}`,
      hardFailed: true,
    };
  }
}

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const founder = await getFounderFromAuth(req);
    if (!founder) {
      return NextResponse.json(
        { error: "Not authenticated" },
        { status: 401 },
      );
    }
    if (!isAudioStorageConfigured()) {
      return NextResponse.json(
        { error: "Supabase Storage not configured." },
        { status: 501 },
      );
    }

    const { id } = await params;
    const body = (await req.json().catch(() => ({}))) as {
      audioDurationSec?: number;
    };

    const upload = await db.upload.findUnique({
      where: { id },
      select: {
        id: true,
        organizationId: true,
        founderId: true,
        filePath: true,
        status: true,
        audioUrl: true,
        textContent: true,
        originalName: true,
        mimeType: true,
        fileSize: true,
      },
    });
    if (!upload) {
      return NextResponse.json({ error: "Upload not found" }, { status: 404 });
    }
    if (upload.organizationId !== founder.organizationId) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }
    if (upload.founderId !== founder.id) {
      return NextResponse.json(
        { error: "Only the uploader can finalize their own upload." },
        { status: 403 },
      );
    }

    // Extract the object path from the `filePath = storage:<path>`
    // sentinel. If someone tampered with the row or this wasn't a
    // storage-backed upload, we refuse.
    const prefix = "storage:";
    if (!upload.filePath || !upload.filePath.startsWith(prefix)) {
      return NextResponse.json(
        {
          error:
            "This upload isn't a storage-backed row. Use /api/upload for small inline files.",
        },
        { status: 400 },
      );
    }
    const objectPath = upload.filePath.slice(prefix.length);

    const isAudio = isAudioUpload(upload.mimeType, upload.originalName);

    // Idempotent: already finalized. Return current state.
    const alreadyFinalized =
      (isAudio && upload.audioUrl) ||
      (!isAudio && upload.textContent);
    if (alreadyFinalized) {
      return NextResponse.json({
        ok: true,
        alreadyFinalized: true,
        audioUrl: upload.audioUrl,
      });
    }

    // Verify the bytes are actually in Storage. Without this a
    // malicious client could POST to /finalize without a real PUT.
    const exists = await audioObjectExists(objectPath);
    if (!exists) {
      return NextResponse.json(
        {
          error:
            "File not present in storage yet. Complete the PUT to the signed URL from /prepare, then retry finalize.",
        },
        { status: 409 },
      );
    }

    const publicUrl = getPublicAudioUrl(objectPath);
    const duration =
      isAudio &&
      body.audioDurationSec &&
      Number.isFinite(body.audioDurationSec)
        ? Math.max(0, Math.floor(body.audioDurationSec))
        : undefined;

    // Updates built up conditionally. For audio we set `audioUrl`.
    // For non-audio we run extraction here so `textContent` is ready
    // by the time Noosphere picks the row up.
    const data: Record<string, unknown> = {
      processLog: {
        set: sanitizeAndCap(
          [
            `— Direct upload reserved —`,
            `— PUT confirmed in storage (${objectPath}) —`,
            isAudio
              ? `— Audio ready; queued for transcription —`
              : `— File ready; running server-side extraction —`,
          ].join("\n"),
          8_000,
        ),
      },
    };

    if (isAudio) {
      data.audioUrl = publicUrl;
      if (duration !== undefined) data.audioDurationSec = duration;
    } else {
      // Non-audio: fetch back + extract. For text uploads the bytes
      // are small and this runs in well under a second; for PDFs /
      // DOCX it's typically 1–5s. Results land directly in the
      // Upload row so Noosphere can ingest without another round-
      // trip.
      const extraction = await extractFromStorage(
        publicUrl!,
        upload.originalName,
        upload.mimeType,
        upload.fileSize,
      );
      data.textContent = extraction.textContent;
      const suffix = `— Extraction: ${extraction.note} —\n`;
      (data.processLog as { set: string }).set = sanitizeAndCap(
        (data.processLog as { set: string }).set + "\n" + suffix,
        8_000,
      );
      if (extraction.hardFailed) {
        data.errorMessage = sanitizeAndCap(extraction.note, 2_000);
      }
    }

    const updated = await db.upload.update({
      where: { id },
      data,
      select: {
        id: true,
        audioUrl: true,
        audioDurationSec: true,
        textContent: true,
        slug: true,
        publishedAt: true,
      },
    });

    // Kick off the Codex → Noosphere pipeline.
    triggerNoosphereProcessing(id, {
      organizationId: founder.organizationId,
      withLlm: true,
    }).catch((err) => {
      console.error(`signed finalize dispatch for ${id} failed:`, err);
    });

    await db.auditEvent
      .create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          uploadId: id,
          action: isAudio ? "audio_upload_finalized" : "file_upload_finalized",
          detail:
            `Direct upload persisted at ${objectPath}; dispatched for processing`,
        },
      })
      .catch(() => {
        /* non-fatal */
      });

    return NextResponse.json({
      ok: true,
      isAudio,
      audioUrl: updated.audioUrl,
      audioDurationSec: updated.audioDurationSec,
      textContentChars: updated.textContent?.length ?? 0,
      publicUrl: updated.slug ? `/post/${updated.slug}` : null,
      published: Boolean(updated.publishedAt),
    });
  } catch (err) {
    console.error("upload/signed/finalize error:", err);
    return NextResponse.json(
      {
        error: `Finalize failed: ${err instanceof Error ? err.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}
