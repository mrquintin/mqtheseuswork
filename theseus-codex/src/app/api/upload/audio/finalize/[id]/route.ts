/**
 * POST /api/upload/audio/finalize/:id
 *
 * Step 2 of 2 for large-audio uploads. The client calls this after
 * it has PUT the audio bytes to the signed URL returned from
 * /api/upload/audio/prepare. We:
 *   1. verify the upload row belongs to the caller;
 *   2. HEAD the object in Supabase Storage to confirm the PUT
 *      actually landed (stops a malicious client from setting
 *      `audioUrl` without uploading anything);
 *   3. set `Upload.audioUrl` to the public URL;
 *   4. fire the normal Noosphere ingest dispatch so Whisper can
 *      transcribe the file into `textContent` and the usual
 *      auto-processing pipeline runs end-to-end.
 *
 * The client can pass `audioDurationSec` if it measured it on the
 * file before upload (via HTMLMediaElement), so the blog index can
 * show "— 47:12 —" next to the play badge.
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import {
  audioObjectExists,
  getPublicAudioUrl,
  isAudioStorageConfigured,
} from "@/lib/supabaseStorage";
import { triggerNoosphereProcessing } from "@/lib/triggerNoosphereProcessing";

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
        {
          error:
            "Only the uploader can finalize their own audio upload.",
        },
        { status: 403 },
      );
    }
    if (upload.audioUrl) {
      // Idempotent: already finalized. Return the same URL so the
      // client can proceed without treating this as an error.
      return NextResponse.json({
        ok: true,
        alreadyFinalized: true,
        audioUrl: upload.audioUrl,
      });
    }

    // Extract the object path from the `filePath = storage:<path>` sentinel
    // we set in /prepare. If someone tampered with the row we refuse to
    // proceed.
    const prefix = "storage:";
    if (!upload.filePath || !upload.filePath.startsWith(prefix)) {
      return NextResponse.json(
        {
          error:
            "This upload isn't a storage-backed audio row. Use /api/upload for small inline files.",
        },
        { status: 400 },
      );
    }
    const objectPath = upload.filePath.slice(prefix.length);

    // Verify the client actually uploaded. Without this check a client
    // could POST to /finalize without a PUT and we'd publish a dead URL.
    const exists = await audioObjectExists(objectPath);
    if (!exists) {
      return NextResponse.json(
        {
          error:
            "Audio object is not present in storage yet. Complete the PUT to the signed URL from /prepare, then retry finalize.",
        },
        { status: 409 },
      );
    }

    const audioUrl = getPublicAudioUrl(objectPath);
    const duration =
      body.audioDurationSec && Number.isFinite(body.audioDurationSec)
        ? Math.max(0, Math.floor(body.audioDurationSec))
        : undefined;

    const updated = await db.upload.update({
      where: { id },
      data: {
        audioUrl,
        ...(duration !== undefined ? { audioDurationSec: duration } : {}),
        processLog: {
          set: [
            `— Audio upload reserved —`,
            `— Audio PUT confirmed in storage (${objectPath}) —`,
            `— Queued for transcription + Noosphere ingest —`,
          ].join("\n"),
        },
      },
      select: {
        id: true,
        audioUrl: true,
        audioDurationSec: true,
        slug: true,
        publishedAt: true,
      },
    });

    // Kick off the normal Codex → Noosphere processing flow so the
    // audio gets transcribed (via Whisper, requires OPENAI_API_KEY on
    // Vercel) and then ingested into conclusions/contradictions just
    // like a text upload. Fire-and-forget; the dashboard polling UI
    // surfaces progress.
    triggerNoosphereProcessing(id, {
      organizationId: founder.organizationId,
      withLlm: true,
    }).catch((err) => {
      console.error(`audio finalize dispatch for ${id} failed:`, err);
    });

    await db.auditEvent
      .create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          uploadId: id,
          action: "audio_upload_finalized",
          detail: `Audio persisted at ${objectPath}; dispatched for transcription`,
        },
      })
      .catch(() => {
        /* non-fatal */
      });

    return NextResponse.json({
      ok: true,
      audioUrl: updated.audioUrl,
      audioDurationSec: updated.audioDurationSec,
      publicUrl: updated.slug ? `/post/${updated.slug}` : null,
      published: Boolean(updated.publishedAt),
    });
  } catch (err) {
    console.error("upload/audio/finalize error:", err);
    return NextResponse.json(
      {
        error:
          `Finalize failed: ${err instanceof Error ? err.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}
