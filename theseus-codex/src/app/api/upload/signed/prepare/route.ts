/**
 * POST /api/upload/signed/prepare
 *
 * Step 1 of 2 for the direct-to-storage upload flow. Works for ANY
 * supported file type — audio, PDF, DOCX, text, transcripts — not
 * just audio. The client POSTs metadata only, we:
 *
 *   1. validate auth + size against the `MAX_UPLOAD_BYTES` cap
 *      (default 500 MB);
 *   2. create an Upload row in `status='pending'` with storage
 *      placeholders;
 *   3. mint a one-shot signed-upload URL on Supabase Storage so the
 *      client can PUT the bytes directly, bypassing Vercel's 4.4 MB
 *      serverless body cap;
 *   4. return `{ uploadId, signedUrl, publicUrl, objectPath, isAudio }`.
 *
 * The client PUTs the file to `signedUrl` from the browser (getting
 * live progress via XHR), then calls
 * `/api/upload/signed/finalize/[id]`.
 *
 * This is the successor to the audio-only
 * `/api/upload/audio/prepare` endpoint. The old path is still
 * registered as a thin shim (see its route.ts) so Dialectic / other
 * external callers that hard-coded it don't break during rollout.
 *
 * If Supabase Storage isn't configured (SUPABASE_URL or
 * SUPABASE_SERVICE_ROLE_KEY missing), returns 501 so the client
 * falls back to the inline `/api/upload` path for small files.
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { canWrite, WRITE_FORBIDDEN_RESPONSE } from "@/lib/roles";
import { sanitizeText, sanitizeAndCap } from "@/lib/sanitizeText";
import { pickAvailableSlug } from "@/lib/slugify";
import {
  createSignedAudioUploadUrl,
  ensureAudioBucketCapacity,
  getAudioBucket,
  isAudioStorageConfigured,
} from "@/lib/supabaseStorage";

/**
 * Hard cap. Defaults to 500 MB so podcast episodes comfortably fit —
 * a 2-hour MP3 at 128 kbps is ~115 MB, a 2-hour WAV is ~1.2 GB
 * (trim it first). Override via env for heavier files, but note
 * that Supabase Storage also has its own per-file size limit
 * configured in the bucket settings — both need to permit the
 * upload for it to succeed. We read `MAX_UPLOAD_BYTES` first, then
 * fall back to the legacy `MAX_AUDIO_BYTES` name for anyone who
 * already set the old env var.
 */
const MAX_UPLOAD_BYTES = Number(
  process.env.MAX_UPLOAD_BYTES ||
    process.env.MAX_AUDIO_BYTES ||
    500 * 1024 * 1024,
);

// Same allow-list the inline /api/upload enforces, plus .aac which
// modern podcast pipelines sometimes emit.
const ALLOWED_EXT = new Set([
  ".md",
  ".markdown",
  ".txt",
  ".vtt",
  ".jsonl",
  ".json",
  ".pdf",
  ".docx",
  ".mp3",
  ".m4a",
  ".wav",
  ".webm",
  ".ogg",
  ".aac",
]);

const AUDIO_EXTS = new Set([
  ".mp3",
  ".m4a",
  ".wav",
  ".webm",
  ".ogg",
  ".aac",
]);

function lowerExt(filename: string): string {
  const i = filename.lastIndexOf(".");
  return i >= 0 ? filename.slice(i).toLowerCase() : "";
}

export async function POST(req: Request) {
  try {
    const founder = await getFounderFromAuth(req);
    if (!founder) {
      return NextResponse.json(
        { error: "Not authenticated" },
        { status: 401 },
      );
    }
    // Role gate: viewers don't get to mint signed URLs either. Without
    // this check the bucket would happily accept a viewer's PUT once
    // we'd handed them the signed URL, since the URL itself carries
    // the auth.
    if (!canWrite(founder.role)) {
      return NextResponse.json(WRITE_FORBIDDEN_RESPONSE, { status: 403 });
    }

    if (!isAudioStorageConfigured()) {
      return NextResponse.json(
        {
          error:
            "Direct upload needs Supabase Storage. Set SUPABASE_URL + " +
            "SUPABASE_SERVICE_ROLE_KEY on Vercel and redeploy, or fall " +
            "back to /api/upload for files under 3.5 MB. See " +
            "docs/Auto_Processing_Setup.md for the walkthrough.",
        },
        { status: 501 },
      );
    }

    const body = (await req.json().catch(() => ({}))) as {
      filename?: string;
      mimeType?: string;
      size?: number;
      // Dialectic (and anything scripted) historically used `fileSize`
      // for the byte count. Accept either so old callers keep working.
      fileSize?: number;
      title?: string;
      description?: string;
      sourceType?: string;
      visibility?: string;
      publishAsPost?: boolean;
      blogExcerpt?: string;
      authorBio?: string;
      audioDurationSec?: number;
      // Dialectic pre-computes a transcript before uploading the
      // trimmed .wav, so the Codex can skip Whisper entirely and jump
      // straight to claim extraction. When present, `textContent` is
      // seeded at prepare-time and `status` starts at `awaiting_ingest`
      // — finalize just persists the audio file reference on top.
      transcript?: string;
      extractionMethod?: string;
      recordedDate?: string;
    };

    const filename = (body.filename || "").trim();
    const size = Number(body.size || body.fileSize || 0);
    const mimeType = (body.mimeType || "").toLowerCase();

    if (!filename) {
      return NextResponse.json(
        { error: "filename is required" },
        { status: 400 },
      );
    }
    if (!size || !Number.isFinite(size) || size <= 0) {
      return NextResponse.json(
        { error: "size (bytes) is required and must be positive" },
        { status: 400 },
      );
    }
    if (size > MAX_UPLOAD_BYTES) {
      return NextResponse.json(
        {
          error:
            `File is ${(size / 1024 / 1024).toFixed(1)} MB — exceeds the ` +
            `${(MAX_UPLOAD_BYTES / 1024 / 1024).toFixed(0)} MB cap. Trim ` +
            `the file or raise MAX_UPLOAD_BYTES on Vercel. Note: ` +
            `Supabase also has a per-file "File size limit" in the ` +
            `bucket settings — raise that too.`,
        },
        { status: 413 },
      );
    }

    // Supabase buckets enforce a per-file cap in addition to our
    // app-level MAX_UPLOAD_BYTES. When the bucket cap is lower than
    // the incoming file, Supabase rejects the direct PUT mid-flight
    // with a 413 "Payload too large" and the user sees a confusing
    // failure after a long upload wait.
    //
    // `ensureAudioBucketCapacity` fixes this by PATCH-ing the bucket
    // to raise its `file_size_limit` to at least the incoming file
    // size (defaulting to 500 MB so small-then-big upload sequences
    // don't trigger a raise every request). The service-role key has
    // admin privileges to do this. Earlier versions of this route
    // called `getAudioBucketFileSizeLimitBytes` and returned 413 if
    // the cap was lower — but if the bucket had no cap set at all
    // (common default), the read returned `null`, we skipped the
    // check, and the user hit the same Supabase-side 413 anyway.
    const ensure = await ensureAudioBucketCapacity(size);
    if (!ensure.ok) {
      const sizeMb = (size / 1024 / 1024).toFixed(1);
      let message: string;
      if (ensure.reason === "unconfigured") {
        message =
          "Supabase Storage is not configured on the server. Set " +
          "SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY on Vercel and " +
          "redeploy, then retry the upload.";
      } else if (ensure.reason === "plan_limit") {
        // The plan-level ceiling is the usual culprit here. On the
        // free tier it's 50 MB; on Pro it's 5 GB. The Storage API
        // refuses to let us raise the bucket's `file_size_limit`
        // above the plan ceiling even as a service-role request —
        // so if both the generous 500 MB target AND the exact file
        // size get rejected, the file genuinely exceeds what the
        // plan permits. We can't fix this in code; the user needs
        // to change one of: the file's size, the Supabase plan,
        // or (eventually) the storage backend itself.
        message =
          `Upload is ${sizeMb} MB, but your Supabase plan refuses ` +
          `to accept files that big. On the free tier the per-file ` +
          `ceiling is 50 MB; on Pro it rises to 5 GB. Three ways out:\n` +
          `  • Upgrade Supabase (Pro is $25/mo, ceiling becomes 5 GB): ` +
          `https://supabase.com/dashboard/project/_/settings/billing\n` +
          `  • Compress the audio below 50 MB — for an ~2 hour podcast, ` +
          `\`ffmpeg -i input.m4a -b:a 32k -ac 1 output.m4a\` usually ` +
          `lands around 30 MB.\n` +
          `  • Split into parts: ` +
          `\`ffmpeg -i input.m4a -f segment -segment_time 3600 -c copy part%d.m4a\` ` +
          `and upload each piece separately.`;
      } else {
        const detailSuffix = ensure.detail
          ? ` Supabase response: ${ensure.detail.slice(0, 200)}`
          : "";
        message =
          `Couldn't raise the Supabase bucket size limit to accept ` +
          `this ${sizeMb} MB file, and the failure isn't the usual ` +
          `plan-ceiling signal. Raise Storage → Bucket settings → ` +
          `File size limit manually, or check the SUPABASE_SERVICE_ROLE_KEY ` +
          `scope.${detailSuffix}`;
      }
      return NextResponse.json({ error: message }, { status: 413 });
    }

    const ext = lowerExt(filename);
    const isAudio =
      mimeType.startsWith("audio/") || AUDIO_EXTS.has(ext);

    if (!ALLOWED_EXT.has(ext) && !isAudio) {
      return NextResponse.json(
        {
          error:
            `Unsupported file type (${ext || mimeType || "unknown"}). ` +
            `Allowed: ${[...ALLOWED_EXT].join(", ")}.`,
        },
        { status: 400 },
      );
    }

    // Visibility / publish parsing — same three-level contract as
    // /api/upload. See Upload.visibility in schema.prisma for the full
    // semantics of each level.
    const rawVisibility = (body.visibility || "org").toLowerCase();
    const visibility: "org" | "semi-private" | "private" =
      rawVisibility === "private"
        ? "private"
        : rawVisibility === "semi-private"
          ? "semi-private"
          : "org";
    const publishAsPost = Boolean(body.publishAsPost);
    if (visibility !== "org" && publishAsPost) {
      return NextResponse.json(
        {
          error:
            visibility === "private"
              ? "An upload can't be both private and published as a blog post. Choose one."
              : "An upload can't be both semi-private and published as a blog post. Choose one.",
        },
        { status: 400 },
      );
    }

    // ── Sanitize + persist minimal metadata on the Upload row.
    const safeTitle =
      sanitizeText(
        (body.title && String(body.title).trim()) ||
          filename.replace(/\.[^/.]+$/, ""),
      ).slice(0, 500) || "Untitled upload";
    const safeDescription = sanitizeAndCap(body.description || "", 10_000);
    const safeOriginalName = sanitizeText(filename).slice(0, 500);
    const safeMime =
      sanitizeText(mimeType || "application/octet-stream").slice(0, 255) ||
      "application/octet-stream";

    // Build a deterministic object path: <upload-id>/<filename-slug>.ext
    // We need the upload id BEFORE creating the row so the signed URL
    // can embed it. Prisma's `@default(cuid())` runs at insert time,
    // which is too late — so we mint a collision-resistant id from
    // Node's crypto primitives and pass it explicitly into create().
    const { randomBytes } = await import("crypto");
    const uploadId = "c" + randomBytes(14).toString("hex").slice(0, 24);
    const safeFilenamePart = filename.replace(/[^A-Za-z0-9._-]+/g, "_");
    const objectPath = `${uploadId}/${safeFilenamePart}`;

    const handle = await createSignedAudioUploadUrl(objectPath);
    if (!handle) {
      return NextResponse.json(
        { error: "Could not mint a signed upload URL." },
        { status: 500 },
      );
    }

    // Publish fields, only if requested and visibility allows.
    let publishFields: {
      publishedAt: Date;
      slug: string;
      blogExcerpt: string | null;
      authorBio: string | null;
    } | null = null;
    if (publishAsPost) {
      const slug = await pickAvailableSlug(safeTitle, async (candidate) => {
        const existing = await db.upload.findUnique({
          where: { slug: candidate },
          select: { id: true },
        });
        return existing !== null;
      });
      publishFields = {
        publishedAt: new Date(),
        slug,
        blogExcerpt: body.blogExcerpt
          ? sanitizeAndCap(body.blogExcerpt, 400)
          : null,
        authorBio: body.authorBio
          ? sanitizeAndCap(body.authorBio, 160)
          : null,
      };
    }

    const duration =
      isAudio &&
      body.audioDurationSec &&
      Number.isFinite(body.audioDurationSec)
        ? Math.max(0, Math.floor(body.audioDurationSec))
        : null;

    // Dialectic pre-attaches the transcript. When present, we seed
    // `textContent` now so `ingest-from-codex` can skip Whisper and run
    // only claim extraction; the status jumps straight to
    // `awaiting_ingest` so the dashboard reflects that extraction is
    // already done before the bytes even land.
    const preAttachedTranscript =
      typeof body.transcript === "string" && body.transcript.trim().length > 0
        ? sanitizeAndCap(body.transcript, 2_000_000)
        : null;
    const preAttachedExtraction =
      typeof body.extractionMethod === "string" && body.extractionMethod.trim()
        ? sanitizeText(body.extractionMethod).slice(0, 64)
        : null;
    const resolvedSourceType = sanitizeText(
      body.sourceType ||
        (preAttachedTranscript ? "transcript" : isAudio ? "audio" : "written"),
    ).slice(0, 64);
    const initialStatus = preAttachedTranscript ? "awaiting_ingest" : "pending";

    const upload = await db.upload.create({
      data: {
        id: uploadId,
        organizationId: founder.organizationId,
        founderId: founder.id,
        title: safeTitle,
        description: safeDescription,
        sourceType: resolvedSourceType,
        originalName: safeOriginalName,
        mimeType: safeMime,
        filePath: `storage:${objectPath}`,
        fileSize: size,
        textContent: preAttachedTranscript,
        extractionMethod: preAttachedExtraction,
        status: initialStatus,
        processLog: sanitizeAndCap(
          `— Direct upload reserved (${(size / 1024 / 1024).toFixed(1)} MB) —\n` +
            `— Awaiting client PUT to Supabase Storage —\n` +
            (preAttachedTranscript
              ? `— Transcript pre-attached (${preAttachedTranscript.length} chars, ` +
                `method=${preAttachedExtraction ?? "unspecified"}); ` +
                `server-side extraction will be skipped —\n`
              : ""),
          8_000,
        ),
        visibility,
        // audioUrl is only set for audio rows, and only after the
        // PUT actually lands (in /finalize). Non-audio rows keep it
        // null.
        audioUrl: null,
        audioDurationSec: duration,
        ...(publishFields ?? {}),
      },
    });

    await db.auditEvent
      .create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          uploadId: upload.id,
          action: "signed_upload_reserved",
          detail:
            `Reserved ${isAudio ? "audio" : "file"} slot for ${safeOriginalName} ` +
            `(${(size / 1024 / 1024).toFixed(1)} MB) at ${objectPath}`,
        },
      })
      .catch(() => {
        /* non-fatal */
      });

    return NextResponse.json({
      uploadId: upload.id,
      signedUrl: handle.signedUrl,
      token: handle.token,
      publicUrl: handle.publicUrl,
      objectPath,
      isAudio,
      // The client includes these in its PUT so Supabase accepts it
      // cleanly regardless of the browser's default Content-Type
      // inference.
      headers: {
        "Content-Type": safeMime,
      },
    });
  } catch (err) {
    console.error("upload/signed/prepare error:", err);
    return NextResponse.json(
      {
        error: `Could not prepare upload: ${err instanceof Error ? err.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}
