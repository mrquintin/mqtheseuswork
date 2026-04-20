/**
 * Minimal client for Supabase Storage via its REST API.
 *
 * We avoid adding `@supabase/supabase-js` because we only need two
 * calls — `createSignedUploadUrl` and `upload` — and pulling in the
 * whole client library would inflate the serverless bundle for a
 * feature that's gated behind env config anyway. The Storage REST API
 * is stable and well-documented at
 * https://supabase.com/docs/guides/storage.
 *
 * Env configuration (both must be set on Vercel for audio uploads
 * to be playable — the blog gracefully degrades to text-only when
 * they're missing):
 *
 *   SUPABASE_URL                 e.g. https://ltuglowgkaircxgjcjvs.supabase.co
 *   SUPABASE_SERVICE_ROLE_KEY    server-side-only key; never ship to the
 *                                 browser. Creates + signs upload URLs.
 *   SUPABASE_AUDIO_BUCKET        bucket name (default: "audio"). MUST be
 *                                 created in the Supabase dashboard and
 *                                 marked public-read.
 */

const DEFAULT_BUCKET = "audio";

/** True when both env vars are set. Used by routes to decide whether
 *  to offer the signed-URL flow or degrade gracefully. */
export function isAudioStorageConfigured(): boolean {
  return Boolean(
    process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY,
  );
}

export function getAudioBucket(): string {
  return process.env.SUPABASE_AUDIO_BUCKET || DEFAULT_BUCKET;
}

function getConfig(): { url: string; key: string; bucket: string } | null {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return null;
  return { url: url.replace(/\/+$/, ""), key, bucket: getAudioBucket() };
}

/** Public CDN URL for an object. Constructed from the bucket + path,
 *  so this doesn't need a network call — safe to call even if the
 *  storage service is unreachable. */
export function getPublicAudioUrl(objectPath: string): string | null {
  const cfg = getConfig();
  if (!cfg) return null;
  return `${cfg.url}/storage/v1/object/public/${encodeURIComponent(
    cfg.bucket,
  )}/${objectPath.split("/").map(encodeURIComponent).join("/")}`;
}

export interface SignedUploadHandle {
  /** One-shot PUT URL the client uses directly from the browser. */
  signedUrl: string;
  /** Opaque token Supabase returns — the client must include it as
   *  `Authorization: Bearer <token>` on the PUT. Newer SDK versions
   *  bake this into the URL; we forward both for compat. */
  token: string;
  /** Path inside the bucket, e.g. "cmo4sd…/podcast.mp3". */
  path: string;
  /** Final public URL after the upload completes. */
  publicUrl: string;
}

/**
 * Ask Supabase for a signed URL the client can PUT to directly, so
 * we don't send large audio through Vercel's 4.4 MB serverless body
 * limit. Returns null when Storage isn't configured so callers can
 * fall back to the "small files only" path without special-casing.
 */
export async function createSignedAudioUploadUrl(
  objectPath: string,
): Promise<SignedUploadHandle | null> {
  const cfg = getConfig();
  if (!cfg) return null;

  const endpoint = `${cfg.url}/storage/v1/object/upload/sign/${encodeURIComponent(
    cfg.bucket,
  )}/${objectPath.split("/").map(encodeURIComponent).join("/")}`;

  const res = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${cfg.key}`,
      apikey: cfg.key,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    const errBody = await res.text().catch(() => "<unreadable>");
    throw new Error(
      `Supabase Storage sign failed: HTTP ${res.status} — ${errBody.slice(0, 240)}`,
    );
  }
  const data = (await res.json()) as { url?: string; token?: string };
  if (!data.url) {
    throw new Error("Supabase Storage sign returned no URL in response.");
  }
  // Supabase's sign endpoint returns a URL *relative to the Storage
  // service*, i.e. "/object/upload/sign/<bucket>/<path>?token=<jwt>".
  // SUPABASE_URL is the project origin ("https://xxx.supabase.co"),
  // NOT the Storage service root ("…/storage/v1"). Naively doing
  // `${cfg.url}${data.url}` produces
  //   https://xxx.supabase.co/object/upload/sign/…
  // which isn't routed to Storage at all — the browser PUT fails
  // as an opaque "Failed to fetch" / CORS error after a long wait.
  //
  // Fix: inject "/storage/v1" when the response is relative. Handle
  // all three shapes defensively in case Supabase changes the API:
  //   - absolute URL                    → use as-is
  //   - starts with "/storage/v1/…"     → prepend origin only
  //   - starts with "/object/…"         → prepend origin + "/storage/v1"
  let signedUrl: string;
  if (data.url.startsWith("http://") || data.url.startsWith("https://")) {
    signedUrl = data.url;
  } else {
    const leading = data.url.startsWith("/") ? data.url : `/${data.url}`;
    signedUrl = leading.startsWith("/storage/v1/")
      ? `${cfg.url}${leading}`
      : `${cfg.url}/storage/v1${leading}`;
  }

  return {
    signedUrl,
    token: data.token || "",
    path: objectPath,
    publicUrl: getPublicAudioUrl(objectPath)!,
  };
}

/**
 * Server-side upload for the small-audio path (files that already
 * fit in the Vercel request body). We still route them through
 * Storage so the blog post has a persistent URL.
 */
export async function uploadAudioBuffer(
  objectPath: string,
  buffer: Uint8Array,
  contentType: string,
): Promise<string | null> {
  const cfg = getConfig();
  if (!cfg) return null;

  const endpoint = `${cfg.url}/storage/v1/object/${encodeURIComponent(
    cfg.bucket,
  )}/${objectPath.split("/").map(encodeURIComponent).join("/")}`;

  // Wrap the Uint8Array in a Blob. TS-strict with lib.dom.d.ts rejects
  // a `Uint8Array<ArrayBufferLike>` as a BlobPart because the buffer
  // could in principle be a SharedArrayBuffer (it isn't, but the type
  // system doesn't know). We copy into a plain ArrayBuffer first, then
  // wrap — adds one allocation, preserves correctness, satisfies TS.
  const ab = new ArrayBuffer(buffer.byteLength);
  new Uint8Array(ab).set(buffer);
  const body = new Blob([ab], {
    type: contentType || "application/octet-stream",
  });

  const res = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${cfg.key}`,
      apikey: cfg.key,
      "Content-Type": contentType || "application/octet-stream",
      // Upsert so re-uploading the same path replaces instead of 409.
      // The object path is `<uploadId>/<filename>` which is unique
      // per upload, so this only matters for retries.
      "x-upsert": "true",
    },
    body,
  });
  if (!res.ok) {
    const errBody = await res.text().catch(() => "<unreadable>");
    throw new Error(
      `Supabase Storage upload failed: HTTP ${res.status} — ${errBody.slice(0, 240)}`,
    );
  }
  return getPublicAudioUrl(objectPath);
}

/**
 * Verify an upload actually landed in Storage. Called by the finalize
 * endpoint before we flip `Upload.audioUrl` — otherwise a client
 * could POST to /finalize without actually uploading the audio and
 * we'd attach a 404 URL to a blog post.
 */
export async function audioObjectExists(objectPath: string): Promise<boolean> {
  const cfg = getConfig();
  if (!cfg) return false;

  const endpoint = `${cfg.url}/storage/v1/object/info/${encodeURIComponent(
    cfg.bucket,
  )}/${objectPath.split("/").map(encodeURIComponent).join("/")}`;

  const res = await fetch(endpoint, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${cfg.key}`,
      apikey: cfg.key,
    },
  });
  return res.ok;
}

/**
 * Best-effort read of the configured bucket's file-size limit, in bytes.
 *
 * Why this exists:
 * - Codex has its own app-level upload cap (`MAX_UPLOAD_BYTES`), but
 *   Supabase buckets can enforce a *lower* per-file cap (often 50 MB by
 *   default).
 * - When the bucket cap is lower, browser PUTs can fail with opaque
 *   "network error" symptoms after waiting.
 *
 * The prepare route can call this to fail fast with an actionable 413
 * before the browser starts a long upload.
 */
export async function getAudioBucketFileSizeLimitBytes(): Promise<number | null> {
  const cfg = getConfig();
  if (!cfg) return null;

  const endpoint = `${cfg.url}/storage/v1/bucket/${encodeURIComponent(
    cfg.bucket,
  )}`;

  const res = await fetch(endpoint, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${cfg.key}`,
      apikey: cfg.key,
    },
  });
  if (!res.ok) return null;

  const data = (await res.json().catch(() => null)) as
    | { file_size_limit?: number | string | null }
    | null;
  if (!data) return null;
  const raw = data.file_size_limit;
  if (raw === null || raw === undefined || raw === "") return null;
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.floor(n);
}

/**
 * Ensure the audio bucket is configured to accept at least
 * `requiredBytes` per file. If the current cap is already high
 * enough, this is a no-op. If the cap is lower (or unset — see the
 * `null` trap below), we PATCH the bucket to raise the cap to
 * `max(requiredBytes, DEFAULT_TARGET)` in one service-role-authed
 * request.
 *
 * Why this is needed
 * ------------------
 * A freshly-created Supabase bucket has `file_size_limit = null`,
 * which the docs describe as "no per-bucket cap" but in practice
 * means "inherits the project's plan-level per-file ceiling". On the
 * free tier that ceiling is 50 MB; on Pro it's 50 GB. Either way
 * `null` is NOT the same as "unlimited", and a size-preflight that
 * reads `null` and skips the check will let an oversized upload
 * start and then fail with an opaque 413 halfway through the PUT.
 *
 * Raising the cap via the admin API turns `null` into an explicit
 * number we control, so subsequent preflights can see it AND the
 * Supabase-side check won't reject the PUT until it hits the actual
 * plan-level ceiling.
 *
 * Failure modes handled:
 * - `cfg` missing → `{ ok: false, reason: "unconfigured" }`.
 * - GET on bucket fails (404, network, etc.) → treat current cap as
 *   unknown and attempt a raise anyway.
 * - PATCH rejected (e.g. plan-level hard ceiling hit) → `{ ok: false,
 *   reason: "plan_limit", currentCapBytes }` so the caller can surface
 *   an actionable "upgrade your Supabase plan" message.
 */
export async function ensureAudioBucketCapacity(requiredBytes: number): Promise<
  | { ok: true; currentCapBytes: number | null; raised: boolean; targetCapBytes: number }
  | { ok: false; reason: "unconfigured" | "plan_limit" | "other"; currentCapBytes: number | null; detail?: string }
> {
  const cfg = getConfig();
  if (!cfg) {
    return { ok: false, reason: "unconfigured", currentCapBytes: null };
  }

  const current = await getAudioBucketFileSizeLimitBytes().catch(() => null);
  // Fast path — the bucket already permits this and larger files.
  if (current !== null && current >= requiredBytes) {
    return {
      ok: true,
      currentCapBytes: current,
      raised: false,
      targetCapBytes: current,
    };
  }

  // We raise to max(requested, 500 MB) so we don't have to re-raise
  // for every slightly-bigger upload. 500 MB matches the app-level
  // MAX_UPLOAD_BYTES default in /api/upload/signed/prepare.
  const DEFAULT_TARGET = 500 * 1024 * 1024;
  const target = Math.max(requiredBytes, DEFAULT_TARGET);

  const endpoint = `${cfg.url}/storage/v1/bucket/${encodeURIComponent(
    cfg.bucket,
  )}`;

  // Supabase Storage accepts PATCH on `/bucket/:id` with a partial
  // body; only the fields you pass are updated. We send file_size_limit
  // only — `public`, `name`, `allowed_mime_types` stay untouched.
  const res = await fetch(endpoint, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${cfg.key}`,
      apikey: cfg.key,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ file_size_limit: target }),
  });

  if (res.ok) {
    return {
      ok: true,
      currentCapBytes: current,
      raised: true,
      targetCapBytes: target,
    };
  }

  // Read the error body for diagnostics. Supabase returns JSON
  // `{ statusCode, error, message }`; anything else we capture as text.
  const errBody = await res.text().catch(() => "");
  // 413 on the PATCH itself means the target exceeds the project's
  // plan-level ceiling. Other 4xx means permissions / misconfig.
  const planCapped =
    res.status === 413 ||
    /plan|limit|exceed/i.test(errBody);
  return {
    ok: false,
    reason: planCapped ? "plan_limit" : "other",
    currentCapBytes: current,
    detail: errBody.slice(0, 400),
  };
}
