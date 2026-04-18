/**
 * POST /api/upload/audio/prepare
 *
 * Step 1 of 2 for large-audio uploads. The client calls this with
 * just the metadata (title, filename, size, visibility flags), we:
 *   1. validate auth + size + that the caller's org is intact;
 *   2. create an Upload row in `status='pending'` with the audio
 *      fields empty;
 *   3. mint a signed-upload URL on Supabase Storage so the client
 *      can PUT the audio bytes directly (bypassing Vercel's 4.4MB
 *      body cap);
 *   4. return `{ uploadId, signedUrl, publicUrl, token }`.
 *
 * The client PUTs the file to `signedUrl` from the browser, then
 * calls `/api/upload/audio/finalize/[id]`.
 *
 * If Supabase Storage isn't configured (SUPABASE_URL /
 * SUPABASE_SERVICE_ROLE_KEY missing on Vercel), this endpoint
 * returns 501 with clear setup instructions so the client falls
 * back to the regular /api/upload path.
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { sanitizeText, sanitizeAndCap } from "@/lib/sanitizeText";
import { pickAvailableSlug } from "@/lib/slugify";
import {
  createSignedAudioUploadUrl,
  isAudioStorageConfigured,
} from "@/lib/supabaseStorage";

// Hard cap to stop a runaway client from reserving an unreasonable
// object. Supabase Storage itself has a 50MB cap per file by default;
// we match that here. Raise via env if the Supabase project is
// configured for larger files.
const MAX_AUDIO_BYTES = Number(
  process.env.MAX_AUDIO_BYTES || 50 * 1024 * 1024,
);

const ALLOWED_AUDIO_EXTS = new Set([
  ".mp3",
  ".m4a",
  ".wav",
  ".webm",
  ".ogg",
  ".aac",
]);

export async function POST(req: Request) {
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
        {
          error:
            "Supabase Storage isn't configured on this deploy. Set " +
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY on Vercel, then " +
            "redeploy. See docs/Auto_Processing_Setup.md for the full " +
            "setup. In the meantime, audio under 3.5 MB works via " +
            "/api/upload.",
        },
        { status: 501 },
      );
    }

    const body = (await req.json().catch(() => ({}))) as {
      filename?: string;
      mimeType?: string;
      size?: number;
      title?: string;
      description?: string;
      sourceType?: string;
      visibility?: string;
      publishAsPost?: boolean;
      blogExcerpt?: string;
      authorBio?: string;
      audioDurationSec?: number;
    };

    const filename = (body.filename || "").trim();
    const size = Number(body.size || 0);
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
    if (size > MAX_AUDIO_BYTES) {
      return NextResponse.json(
        {
          error:
            `File is ${(size / 1024 / 1024).toFixed(1)} MB — exceeds the ` +
            `${(MAX_AUDIO_BYTES / 1024 / 1024).toFixed(0)} MB cap for audio ` +
            `uploads. Trim the episode or raise MAX_AUDIO_BYTES on Vercel.`,
        },
        { status: 413 },
      );
    }
    const ext = filename.slice(filename.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED_AUDIO_EXTS.has(ext) && !mimeType.startsWith("audio/")) {
      return NextResponse.json(
        {
          error:
            `Unsupported audio type (${ext || mimeType || "unknown"}). ` +
            `Allowed: ${[...ALLOWED_AUDIO_EXTS].join(", ")}.`,
        },
        { status: 400 },
      );
    }

    // Visibility / publish parsing — same contract as /api/upload.
    const visibility: "org" | "private" =
      (body.visibility || "org").toLowerCase() === "private"
        ? "private"
        : "org";
    const publishAsPost = Boolean(body.publishAsPost);
    if (visibility === "private" && publishAsPost) {
      return NextResponse.json(
        {
          error:
            "An upload can't be both private and published as a blog post. Choose one.",
        },
        { status: 400 },
      );
    }

    // ── Sanitize + persist minimal metadata on the Upload row.
    const safeTitle =
      sanitizeText(
        (body.title && String(body.title).trim()) ||
          filename.replace(/\.[^/.]+$/, ""),
      ).slice(0, 500) || "Untitled audio";
    const safeDescription = sanitizeAndCap(body.description || "", 10_000);
    const safeOriginalName = sanitizeText(filename).slice(0, 500);
    const safeMime =
      sanitizeText(mimeType || "audio/mpeg").slice(0, 255) || "audio/mpeg";

    // Build a deterministic object path: <upload-id>/<filename-slug>.ext
    // We need the upload id BEFORE creating the row so the signed URL
    // can embed it. Prisma's `@default(cuid())` runs at insert time,
    // which is too late — so we generate a collision-resistant id
    // here from Node's crypto primitives and pass it explicitly into
    // create(). The shape ("c" + 24 hex chars) is visually compatible
    // with cuid output and collision-safe for this call volume.
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
      body.audioDurationSec && Number.isFinite(body.audioDurationSec)
        ? Math.max(0, Math.floor(body.audioDurationSec))
        : null;

    const upload = await db.upload.create({
      data: {
        id: uploadId,
        organizationId: founder.organizationId,
        founderId: founder.id,
        title: safeTitle,
        description: safeDescription,
        sourceType: sanitizeText(body.sourceType || "audio").slice(0, 64),
        originalName: safeOriginalName,
        mimeType: safeMime,
        filePath: `storage:${objectPath}`,
        fileSize: size,
        status: "pending",
        processLog: sanitizeAndCap(
          `— Audio upload reserved (${(size / 1024 / 1024).toFixed(1)} MB) —\n` +
            `— Waiting for client to PUT to Supabase Storage —\n`,
          8_000,
        ),
        visibility,
        audioUrl: null, // set by /finalize after the PUT succeeds
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
          action: "audio_upload_reserved",
          detail: `Reserved audio slot for ${safeOriginalName} (${(size / 1024 / 1024).toFixed(1)} MB) at ${objectPath}`,
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
      // The client includes these in its PUT so Supabase's API accepts the
      // upload cleanly.
      headers: {
        "x-upsert": "true",
        "Content-Type": safeMime,
      },
    });
  } catch (err) {
    console.error("upload/audio/prepare error:", err);
    return NextResponse.json(
      {
        error:
          `Could not prepare audio upload: ${err instanceof Error ? err.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}
