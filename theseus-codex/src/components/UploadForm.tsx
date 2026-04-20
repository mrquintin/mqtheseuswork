"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";

const ACCEPTED_EXTENSIONS =
  ".txt,.md,.markdown,.pdf,.docx,.vtt,.jsonl,.mp3,.m4a,.wav,.webm,.ogg,.aac";

/**
 * Read the duration of an audio File in the browser by mounting an
 * offscreen HTMLAudioElement and waiting for `loadedmetadata`. Returns
 * the duration in whole seconds, or rejects after a timeout / if the
 * browser can't decode the file. Used to pre-fill
 * `Upload.audioDurationSec` so published episodes show "— 47:12 —"
 * badges on the blog index.
 */
async function probeAudioDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const el = document.createElement("audio");
    const url = URL.createObjectURL(file);
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("duration probe timeout"));
    }, 6000);
    const cleanup = () => {
      window.clearTimeout(timer);
      URL.revokeObjectURL(url);
      el.src = "";
    };
    el.preload = "metadata";
    el.onloadedmetadata = () => {
      const d = el.duration;
      cleanup();
      if (!Number.isFinite(d) || d <= 0) {
        reject(new Error("invalid duration"));
      } else {
        resolve(Math.round(d));
      }
    };
    el.onerror = () => {
      cleanup();
      reject(new Error("audio load failed"));
    };
    el.src = url;
  });
}

// ─────────────────────────────────────────────────────────────────────
// Queue model — one UploadItem per pending/in-flight/finished upload.
// ─────────────────────────────────────────────────────────────────────
//
// A dropped file becomes an UploadItem with phase="queued". On submit,
// we walk the queue sequentially: each item moves through preparing →
// uploading → finalizing → processing → ingested|failed. All items
// share the batch-level metadata below (description, visibility,
// publish-as-post, excerpt, byline). Per-item metadata (title,
// sourceType) is derived from the filename and MIME type by default;
// the user can edit them only in single-file mode to keep the bulk
// UI uncluttered.

type ItemPhase =
  | "queued"      // in the queue, upload not yet started
  | "preparing"   // signed-flow only — calling /api/upload/signed/prepare
  | "uploading"   // bytes in flight (either inline POST or direct PUT)
  | "finalizing"  // signed-flow only — calling /finalize/[id]
  | "processing"  // upload accepted, awaiting Noosphere ingestion
  | "ingested"    // terminal: success
  | "failed";     // terminal: error

interface UploadItem {
  id: string;           // local uuid for React keys
  file: File;
  title: string;
  sourceType: string;
  phase: ItemPhase;
  progressFrac: number; // 0..1 during "uploading" phase
  progressBytes?: string;
  uploadId?: string;    // server-assigned after prepare/inline
  claimsCount?: number;
  publicUrl?: string;
  errorMessage?: string;
  serverStatus?: string; // raw status string from /api/upload/:id
}

function itemIsTerminal(p: ItemPhase): boolean {
  return p === "ingested" || p === "failed";
}

function deriveTitleFromFilename(name: string): string {
  return name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " ");
}

function deriveSourceTypeFromFile(f: File): string {
  if (f.type.startsWith("audio/")) return "audio";
  return "written";
}

function isAudioFile(f: File): boolean {
  return (
    f.type.startsWith("audio/") ||
    /\.(mp3|m4a|wav|webm|ogg|aac)$/i.test(f.name)
  );
}

/** Files ≤ this go through the single-POST inline flow; larger files
 *  take the three-step signed-URL flow that bypasses Vercel's 4.4 MB
 *  body cap. Audio ALWAYS takes signed so we have a persistent
 *  `audioUrl` for playback regardless of size. */
const INLINE_MAX = 3.5 * 1024 * 1024;

/** Tight human bytes for the queue row — "84 KB", "12.3 MB". */
function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const PHASE_LABEL: Record<ItemPhase, string> = {
  queued: "Queued",
  preparing: "Preparing",
  uploading: "Uploading",
  finalizing: "Finalizing",
  processing: "Processing",
  ingested: "Ingested",
  failed: "Failed",
};

const PHASE_COLOR: Record<ItemPhase, string> = {
  queued: "var(--amber-dim)",
  preparing: "var(--amber)",
  uploading: "var(--amber)",
  finalizing: "var(--amber)",
  processing: "var(--amber)",
  ingested: "var(--success)",
  failed: "var(--ember)",
};

/**
 * Upload form.
 *
 * Visual
 * ------
 * The Augustus Prima Porta sculpture now lives as a half-page backdrop (see
 * UploadPage in app/(authed)/upload/page.tsx + SculptureBackdrop). This
 * component is just the form itself; the patron sculpture is the room
 * it sits in.
 *
 * Bulk upload
 * -----------
 * Drop (or pick) one file → the classic single-file UI with an
 * editable title. Drop 2+ files → a queue view: per-row status,
 * per-row progress bar while bytes are in flight, per-row error on
 * failure. Shared metadata (description, visibility, publish flag,
 * excerpt, byline) applies to every item in the batch; titles are
 * auto-derived from filenames and can be edited from /library after
 * ingest. Uploads run sequentially to keep progress legible and avoid
 * thrashing the prepare endpoint; status polling runs concurrently
 * once all bytes have landed.
 *
 * Vercel-compat copy
 * ------------------
 * Earlier copy mentioned `python -m noosphere ingest`, which is only
 * true for self-hosted deploys. Neutral phrasing here; the scribe's
 * log (polled after submit) reports the real status.
 */
export default function UploadForm() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragover, setDragover] = useState(false);

  // ── Queue ──────────────────────────────────────────────────────
  const [items, setItems] = useState<UploadItem[]>([]);
  // Latest-ref pattern: the polling effect reads the current items
  // through this ref so it doesn't re-create intervals on every item
  // update (which happens many times per second during upload).
  const itemsRef = useRef(items);
  itemsRef.current = items;

  // ── Shared metadata (all items in the batch) ───────────────────
  const [description, setDescription] = useState("");
  const [publishAsPost, setPublishAsPost] = useState(false);
  const [blogExcerpt, setBlogExcerpt] = useState("");
  const [authorBio, setAuthorBio] = useState("");
  const [privateUpload, setPrivateUpload] = useState(false);

  // ── Top-level form state ───────────────────────────────────────
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const updateItem = useCallback(
    (id: string, patch: Partial<UploadItem>) => {
      setItems((prev) =>
        prev.map((it) => (it.id === id ? { ...it, ...patch } : it)),
      );
    },
    [],
  );

  const addFiles = useCallback(
    (files: FileList | File[]) => {
      const list = Array.from(files);
      if (list.length === 0) return;
      setItems((prev) => {
        // Dedupe by (name, size) against already-queued items so
        // dropping the same file twice doesn't create a duplicate row.
        const seen = new Set(
          prev.map((it) => `${it.file.name}|${it.file.size}`),
        );
        const additions: UploadItem[] = [];
        for (const f of list) {
          const key = `${f.name}|${f.size}`;
          if (seen.has(key)) continue;
          seen.add(key);
          additions.push({
            id:
              typeof crypto !== "undefined" && "randomUUID" in crypto
                ? crypto.randomUUID()
                : `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
            file: f,
            title: deriveTitleFromFilename(f.name),
            sourceType: deriveSourceTypeFromFile(f),
            phase: "queued",
            progressFrac: 0,
          });
        }
        return additions.length === 0 ? prev : [...prev, ...additions];
      });
    },
    [],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragover(false);
      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    },
    [addFiles],
  );

  const removeItem = useCallback((id: string) => {
    setItems((prev) => prev.filter((it) => it.id !== id));
  }, []);

  const clearQueue = useCallback(() => {
    setItems([]);
    setError("");
    setSuccess("");
  }, []);

  // ── Inline flow: one POST, bytes in request body (≤ 3.5 MB) ────
  async function runInline(item: UploadItem): Promise<string> {
    updateItem(item.id, { phase: "uploading", progressFrac: 0.1 });
    const fd = new FormData();
    fd.append("file", item.file);
    fd.append("title", item.title);
    fd.append("description", description);
    fd.append("sourceType", item.sourceType);
    fd.append("publishAsPost", publishAsPost ? "1" : "0");
    if (publishAsPost) {
      fd.append("blogExcerpt", blogExcerpt.trim());
      fd.append("authorBio", authorBio.trim());
    }
    fd.append("visibility", privateUpload ? "private" : "org");

    const res = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "Upload failed");
    }
    return data.id as string;
  }

  // ── Signed flow: prepare → direct PUT to Supabase → finalize ───
  async function runSigned(
    item: UploadItem,
    opts: { isAudio: boolean },
  ): Promise<string> {
    const f = item.file;
    updateItem(item.id, { phase: "preparing", progressFrac: 0 });

    const audioDurationSec = opts.isAudio
      ? await probeAudioDuration(f).catch(() => null)
      : null;

    const prepareBody = {
      filename: f.name,
      mimeType:
        f.type || (opts.isAudio ? "audio/mpeg" : "application/octet-stream"),
      size: f.size,
      title: item.title,
      description,
      sourceType:
        item.sourceType || (opts.isAudio ? "audio" : "written"),
      visibility: privateUpload ? "private" : "org",
      publishAsPost,
      blogExcerpt: publishAsPost ? blogExcerpt.trim() : "",
      authorBio: publishAsPost ? authorBio.trim() : "",
      audioDurationSec,
    };
    const prep = await fetch("/api/upload/signed/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prepareBody),
    });
    const prepData = await prep.json();
    if (!prep.ok) {
      throw new Error(prepData.error || `Prepare failed (${prep.status})`);
    }
    const { uploadId, signedUrl, headers: putHeaders } = prepData as {
      uploadId: string;
      signedUrl: string;
      headers?: Record<string, string>;
    };

    const totalMB = (f.size / 1024 / 1024).toFixed(1);
    updateItem(item.id, {
      phase: "uploading",
      uploadId,
      progressFrac: 0,
      progressBytes: `0 MB / ${totalMB} MB`,
    });

    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", signedUrl);
      const ct =
        (putHeaders && putHeaders["Content-Type"]) ||
        f.type ||
        "application/octet-stream";
      // Keep the PUT a "simple" CORS request: only `Content-Type`.
      // The signed URL carries the JWT as `?token=<jwt>`, so no
      // Authorization header is needed (and adding one would trigger
      // a preflight OPTIONS that doesn't always succeed).
      xhr.setRequestHeader("Content-Type", ct);
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable) {
          const frac = ev.loaded / ev.total;
          updateItem(item.id, {
            progressFrac: frac,
            progressBytes: `${(ev.loaded / 1024 / 1024).toFixed(1)} MB / ${totalMB} MB`,
          });
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          updateItem(item.id, { progressFrac: 1 });
          resolve();
        } else {
          reject(
            new Error(
              `Direct upload failed (${xhr.status}): ${(xhr.responseText || "").slice(0, 180)}`,
            ),
          );
        }
      };
      xhr.onerror = () =>
        reject(
          new Error(
            "Direct upload failed: network/CORS error. " +
              "Check Supabase bucket CORS + file-size limit.",
          ),
        );
      xhr.onabort = () =>
        reject(new Error("Upload aborted"));
      xhr.ontimeout = () =>
        reject(new Error("Upload timed out"));
      xhr.send(f);
    });

    updateItem(item.id, { phase: "finalizing" });
    const fin = await fetch(`/api/upload/signed/finalize/${uploadId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audioDurationSec }),
    });
    const finData = await fin.json();
    if (!fin.ok) {
      throw new Error(finData.error || `Finalize failed (${fin.status})`);
    }
    return uploadId;
  }

  async function runOne(item: UploadItem): Promise<void> {
    try {
      const audio = isAudioFile(item.file);
      const useSigned = audio || item.file.size > INLINE_MAX;
      const uploadId = useSigned
        ? await runSigned(item, { isAudio: audio })
        : await runInline(item);
      updateItem(item.id, {
        phase: "processing",
        uploadId,
        progressFrac: 1,
      });
    } catch (err) {
      updateItem(item.id, {
        phase: "failed",
        errorMessage: err instanceof Error ? err.message : String(err),
      });
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (items.length === 0) {
      setError("Drop at least one file to upload.");
      return;
    }
    setError("");
    setSuccess("");
    setUploading(true);

    // Sequential upload. For text-y files each takes ~1s, so even a
    // 20-file drop finishes the upload phase in well under a minute.
    // For audio / large files, sequential is what you want anyway —
    // parallel PUTs would just starve each other of bandwidth.
    const snapshot = items.slice();
    for (const item of snapshot) {
      if (itemIsTerminal(item.phase) || item.phase === "processing") continue;
      // Re-read the latest version from the queue in case the user
      // removed it mid-batch. (Harmless to skip missing rows.)
      const fresh = itemsRef.current.find((it) => it.id === item.id);
      if (!fresh) continue;
      await runOne(fresh);
    }

    setSuccess(
      items.length > 1
        ? `All ${items.length} uploads received — awaiting Noosphere…`
        : "Upload received. Noosphere is processing in the cloud…",
    );
  }

  // ── Status polling: drives "processing → ingested|failed" ──────
  //
  // Started when `uploading` flips to true; tears down when every
  // item has reached a terminal phase. Uses the latest-ref pattern
  // so it doesn't restart on every item update — the interval reads
  // `itemsRef.current` each tick.
  useEffect(() => {
    if (!uploading) return;

    const iv = window.setInterval(async () => {
      const now = itemsRef.current;
      const toPoll = now.filter(
        (it) => it.phase === "processing" && it.uploadId,
      );

      // All items terminal? Stop.
      if (
        toPoll.length === 0 &&
        now.length > 0 &&
        now.every((it) => itemIsTerminal(it.phase))
      ) {
        window.clearInterval(iv);
        setUploading(false);
        const good = now.filter((it) => it.phase === "ingested").length;
        const bad = now.filter((it) => it.phase === "failed").length;
        if (bad === 0) {
          const totalClaims = now.reduce(
            (n, it) => n + (it.claimsCount ?? 0),
            0,
          );
          setSuccess(
            good === 1
              ? `Ingest complete — ${totalClaims} claim(s) extracted. Redirecting…`
              : `All ${good} contributions ingested — ${totalClaims} claim(s) total. Redirecting…`,
          );
          // Auto-redirect on clean runs, same as the pre-bulk UX.
          window.setTimeout(() => router.push("/dashboard"), 2600);
        } else if (good === 0) {
          setError(
            `All ${bad} upload(s) failed. See per-file errors below.`,
          );
          setSuccess("");
        } else {
          setSuccess(
            `${good} ingested, ${bad} failed. Check the errors below; succeeded uploads are already in /library.`,
          );
        }
        return;
      }

      // Poll each processing item in parallel.
      await Promise.all(
        toPoll.map(async (it) => {
          try {
            const pr = await fetch(`/api/upload/${it.uploadId}`);
            if (!pr.ok) return;
            const u = (await pr.json()) as {
              status?: string;
              errorMessage?: string | null;
              claimsCount?: number;
              publicUrl?: string | null;
            };
            const patch: Partial<UploadItem> = { serverStatus: u.status };
            if (u.status === "ingested") {
              patch.phase = "ingested";
              patch.claimsCount = u.claimsCount ?? 0;
              if (u.publicUrl) patch.publicUrl = u.publicUrl;
            } else if (u.status === "failed") {
              patch.phase = "failed";
              patch.errorMessage =
                u.errorMessage || "Noosphere reported failure";
            }
            updateItem(it.id, patch);
          } catch {
            // Non-fatal; keep polling.
          }
        }),
      );
    }, 2000);

    // Hard cap — 15 min for a batch; individual workflow timeout is
    // 25 min but the user shouldn't watch a spinner that long.
    const hardStop = window.setTimeout(() => {
      window.clearInterval(iv);
      setUploading(false);
    }, 900_000);

    return () => {
      window.clearInterval(iv);
      window.clearTimeout(hardStop);
    };
  }, [uploading, router, updateItem]);

  // ───────────────────────────────────────────────────────────────
  // Render
  // ───────────────────────────────────────────────────────────────
  const hasItems = items.length > 0;
  const isBulk = items.length > 1;
  const committing = uploading;
  const commitLabel = committing
    ? "Committing…"
    : isBulk
      ? `Commit ${items.length} contributions`
      : "Commit to the Codex";

  return (
    <main
      style={{
        maxWidth: "680px",
        // Offset the form to the right so it doesn't overlap the Augustus
        // backdrop sitting on the left. `marginLeft: auto` keeps it
        // right-aligned within the page's centred column; on smaller
        // viewports the `max-width: 900px` media query in
        // SculptureBackdrop hides the sculpture, so auto-centring resumes.
        margin: "2rem 2rem 3rem auto",
        padding: "0 2rem",
      }}
    >
      <header style={{ marginBottom: "2rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            fontSize: "1.8rem",
            letterSpacing: "0.18em",
            color: "var(--amber)",
            textShadow: "var(--glow-md)",
            margin: 0,
          }}
        >
          Dedicatio
        </h1>
        <p
          className="mono"
          style={{
            fontSize: "0.62rem",
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginTop: "0.25rem",
            marginBottom: 0,
          }}
        >
          Upload Contribution · Augustus Prima Porta
        </p>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "1rem",
            color: "var(--parchment-dim)",
            marginTop: "0.5rem",
            marginBottom: 0,
            lineHeight: 1.55,
            maxWidth: "44em",
          }}
        >
          Commit a transcript, essay, or session — or several at once.
          Markdown, plain text, WebVTT, Dialectic JSONL, PDF, DOCX, and
          common audio formats are accepted.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}
      >
        <div
          className={`upload-zone ${dragover ? "dragover" : ""}`}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragover(true);
          }}
          onDragLeave={() => setDragover(false)}
          onDrop={handleDrop}
          style={{
            position: "relative",
            minHeight: "140px",
            padding: "1.25rem 1.5rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
          }}
        >
          <input
            ref={fileRef}
            type="file"
            multiple
            accept={ACCEPTED_EXTENSIONS}
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) {
                addFiles(e.target.files);
                // Clear the input so re-selecting the same filename
                // after removing it from the queue still fires change.
                e.target.value = "";
              }
            }}
          />

          <div>
            <p
              className="mono"
              style={{
                fontSize: "0.62rem",
                letterSpacing: "0.3em",
                textTransform: "uppercase",
                color: hasItems ? "var(--ember)" : "var(--amber-dim)",
                margin: 0,
              }}
            >
              {hasItems ? "Liber Apertus · In Queue" : "Liber Apertus"}
            </p>
            <p
              style={{
                fontFamily: "'EB Garamond', serif",
                fontSize: "1.05rem",
                fontStyle: "italic",
                color: "var(--parchment)",
                marginTop: "0.4rem",
                marginBottom: 0,
              }}
            >
              {hasItems
                ? isBulk
                  ? `${items.length} files queued — drop more or click to add.`
                  : "One file queued — drop more or click to add."
                : "Drop files here, or click to browse. Multiple files are welcome."}
            </p>
          </div>
        </div>

        {/* ── Queue display ────────────────────────────────────── */}
        {hasItems && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem",
              padding: "0.9rem 1rem",
              border: "1px solid var(--stroke)",
              borderRadius: "4px",
              background: "rgba(212, 160, 23, 0.035)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                marginBottom: "0.2rem",
              }}
            >
              <span
                className="mono"
                style={{
                  fontSize: "0.62rem",
                  letterSpacing: "0.24em",
                  textTransform: "uppercase",
                  color: "var(--amber-dim)",
                }}
              >
                {isBulk ? `${items.length} files · Queue` : "File · Sigillatum"}
              </span>
              {!committing && (
                <button
                  type="button"
                  onClick={clearQueue}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--amber-dim)",
                    fontSize: "0.72rem",
                    cursor: "pointer",
                    padding: "0.2rem 0.4rem",
                  }}
                >
                  Clear queue
                </button>
              )}
            </div>

            <ul
              style={{
                listStyle: "none",
                margin: 0,
                padding: 0,
                display: "flex",
                flexDirection: "column",
                gap: "0.55rem",
              }}
            >
              {items.map((it) => (
                <li
                  key={it.id}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.28rem",
                    padding: "0.55rem 0.7rem",
                    border: `1px solid ${
                      it.phase === "failed"
                        ? "var(--ember)"
                        : it.phase === "ingested"
                          ? "var(--success)"
                          : "rgba(212, 160, 23, 0.16)"
                    }`,
                    borderRadius: "3px",
                    background: "rgba(12, 8, 4, 0.35)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      gap: "0.8rem",
                      alignItems: "baseline",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "'EB Garamond', serif",
                        fontSize: "0.98rem",
                        color: "var(--amber)",
                        flex: 1,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={it.file.name}
                    >
                      {it.file.name}
                    </span>
                    <span
                      className="mono"
                      style={{
                        fontSize: "0.66rem",
                        letterSpacing: "0.08em",
                        color: "var(--parchment-dim)",
                      }}
                    >
                      {humanBytes(it.file.size)}
                    </span>
                    <span
                      className="mono"
                      style={{
                        fontSize: "0.64rem",
                        letterSpacing: "0.2em",
                        textTransform: "uppercase",
                        color: PHASE_COLOR[it.phase],
                        minWidth: "5.5em",
                        textAlign: "right",
                      }}
                    >
                      {PHASE_LABEL[it.phase]}
                    </span>
                    {!committing && it.phase === "queued" && (
                      <button
                        type="button"
                        onClick={() => removeItem(it.id)}
                        aria-label={`Remove ${it.file.name}`}
                        style={{
                          background: "none",
                          border: "none",
                          color: "var(--amber-dim)",
                          fontSize: "1rem",
                          lineHeight: 1,
                          cursor: "pointer",
                          padding: "0 0.3rem",
                        }}
                      >
                        ×
                      </button>
                    )}
                  </div>

                  {/* Live progress bar while bytes are moving */}
                  {(it.phase === "uploading" ||
                    it.phase === "preparing" ||
                    it.phase === "finalizing") && (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.2rem",
                      }}
                    >
                      <div
                        style={{
                          height: "4px",
                          borderRadius: "2px",
                          background: "rgba(212, 160, 23, 0.12)",
                          overflow: "hidden",
                        }}
                        aria-hidden
                      >
                        <div
                          style={{
                            width: `${Math.min(100, Math.max(0, it.progressFrac * 100)).toFixed(1)}%`,
                            height: "100%",
                            background:
                              "linear-gradient(90deg, var(--amber-dim), var(--amber))",
                            transition: "width 0.18s ease",
                          }}
                        />
                      </div>
                      {it.progressBytes && (
                        <span
                          className="mono"
                          style={{
                            fontSize: "0.62rem",
                            color: "var(--amber-dim)",
                          }}
                        >
                          {it.progressBytes}
                        </span>
                      )}
                    </div>
                  )}

                  {it.phase === "processing" && (
                    <p
                      style={{
                        margin: 0,
                        fontSize: "0.78rem",
                        color: "var(--parchment-dim)",
                        fontStyle: "italic",
                      }}
                    >
                      Noosphere is analyzing this upload…
                    </p>
                  )}

                  {it.phase === "ingested" && (
                    <p
                      style={{
                        margin: 0,
                        fontSize: "0.8rem",
                        color: "var(--success)",
                      }}
                    >
                      Ingested · {it.claimsCount ?? 0} claim(s) extracted
                      {it.publicUrl ? (
                        <>
                          {" · "}
                          <a
                            href={it.publicUrl}
                            style={{
                              color: "var(--amber)",
                              textDecoration: "underline",
                            }}
                          >
                            view post
                          </a>
                        </>
                      ) : null}
                    </p>
                  )}

                  {it.phase === "failed" && (
                    <p
                      style={{
                        margin: 0,
                        fontSize: "0.8rem",
                        color: "var(--ember)",
                      }}
                    >
                      {it.errorMessage || "Unknown error"}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ── Title — single-file only; bulk titles derive from names ─── */}
        {hasItems && !isBulk && (
          <div>
            <label
              className="mono"
              style={{
                fontSize: "0.65rem",
                letterSpacing: "0.2em",
                textTransform: "uppercase",
                color: "var(--amber-dim)",
                display: "block",
                marginBottom: "0.4rem",
              }}
            >
              Title
            </label>
            <input
              type="text"
              value={items[0]?.title ?? ""}
              onChange={(e) =>
                items[0] && updateItem(items[0].id, { title: e.target.value })
              }
              required
            />
          </div>
        )}

        {isBulk && (
          <p
            className="mono"
            style={{
              fontSize: "0.72rem",
              color: "var(--parchment-dim)",
              margin: "0 0 -0.5rem",
              lineHeight: 1.55,
              fontStyle: "italic",
            }}
          >
            Titles are derived from each filename. Edit individual titles
            from{" "}
            <code
              className="mono"
              style={{ color: "var(--amber-dim)", fontSize: "0.78rem" }}
            >
              /library
            </code>{" "}
            after ingest. The description, visibility, and publication
            settings below apply to every file in the batch.
          </p>
        )}

        <div>
          <label
            className="mono"
            style={{
              fontSize: "0.65rem",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              display: "block",
              marginBottom: "0.4rem",
            }}
          >
            Description (optional)
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
          />
        </div>

        {/* Type selector — single-file only. In bulk mode the per-file
            source type derives from each file's MIME / extension, so
            exposing a single dropdown would be misleading (it would
            apply to all files, overriding the inferred types). */}
        {hasItems && !isBulk && (
          <div>
            <label
              className="mono"
              style={{
                fontSize: "0.65rem",
                letterSpacing: "0.2em",
                textTransform: "uppercase",
                color: "var(--amber-dim)",
                display: "block",
                marginBottom: "0.4rem",
              }}
            >
              Type
            </label>
            <select
              value={items[0]?.sourceType ?? "written"}
              onChange={(e) =>
                items[0] &&
                updateItem(items[0].id, { sourceType: e.target.value })
              }
            >
              <option value="written">Written</option>
              <option value="annotation">Annotation</option>
              <option value="external">External</option>
              <option value="audio">Audio</option>
              <option value="transcript">Transcript</option>
            </select>
          </div>
        )}

        {/* ── Visibility + publication toggles ─────────────────────── */}
        {/* Two independent privacy axes:                              */}
        {/*   1. Private      → only you see it in /library. Noosphere */}
        {/*                      still ingests it so YOU get the       */}
        {/*                      conclusions, but peers don't see the  */}
        {/*                      upload or its excerpt.                */}
        {/*   2. Publish      → public blog post at / + /post/:slug.   */}
        {/* Both default OFF (firm-shared, not public). The checkboxes */}
        {/* are mutually exclusive — a blog post cannot be private and */}
        {/* vice versa — which the UI enforces by disabling/clearing   */}
        {/* whichever box is incompatible with the one just clicked.   */}
        <div
          style={{
            marginTop: "0.5rem",
            padding: "1rem 1.1rem",
            border: "1px solid var(--stroke)",
            borderRadius: "4px",
            background: "rgba(212, 160, 23, 0.035)",
            display: "flex",
            flexDirection: "column",
            gap: "0.8rem",
          }}
        >
          <label
            style={{
              display: "flex",
              gap: "0.65rem",
              alignItems: "flex-start",
              cursor: publishAsPost ? "not-allowed" : "pointer",
              opacity: publishAsPost ? 0.55 : 1,
            }}
          >
            <input
              type="checkbox"
              checked={privateUpload}
              disabled={publishAsPost}
              onChange={(e) => {
                const checked = e.target.checked;
                setPrivateUpload(checked);
                if (checked && publishAsPost) setPublishAsPost(false);
              }}
              style={{
                marginTop: "0.22rem",
                accentColor: "var(--amber)",
                width: "1rem",
                height: "1rem",
              }}
            />
            <span style={{ display: "block" }}>
              <span
                className="mono"
                style={{
                  fontSize: "0.66rem",
                  letterSpacing: "0.24em",
                  textTransform: "uppercase",
                  color: "var(--amber)",
                  display: "block",
                  marginBottom: "0.2rem",
                }}
              >
                {isBulk ? "Private upload (all files)" : "Private upload"}
              </span>
              <span
                style={{
                  fontFamily: "'EB Garamond', serif",
                  fontSize: "0.92rem",
                  color: "var(--parchment-dim)",
                  lineHeight: 1.5,
                }}
              >
                {`Only you will see ${isBulk ? "these files" : "this file"} in `}
                <code
                  className="mono"
                  style={{ fontSize: "0.78rem", color: "var(--amber-dim)" }}
                >
                  /library
                </code>
                {`. Noosphere still analyses ${
                  isBulk ? "them" : "it"
                } for your conclusions, contradictions, and open questions, but other founders in the firm can\u2019t read, view, or request deletion. You can lift the veil later from the dashboard.`}
              </span>
            </span>
          </label>

          <label
            style={{
              display: "flex",
              gap: "0.65rem",
              alignItems: "flex-start",
              cursor: privateUpload ? "not-allowed" : "pointer",
              opacity: privateUpload ? 0.55 : 1,
            }}
          >
            <input
              type="checkbox"
              checked={publishAsPost}
              disabled={privateUpload}
              onChange={(e) => {
                const checked = e.target.checked;
                setPublishAsPost(checked);
                if (checked && privateUpload) setPrivateUpload(false);
              }}
              style={{
                marginTop: "0.22rem",
                accentColor: "var(--amber)",
                width: "1rem",
                height: "1rem",
              }}
            />
            <span style={{ display: "block" }}>
              <span
                className="mono"
                style={{
                  fontSize: "0.66rem",
                  letterSpacing: "0.24em",
                  textTransform: "uppercase",
                  color: "var(--amber)",
                  display: "block",
                  marginBottom: "0.2rem",
                }}
              >
                {isBulk
                  ? "Publish as blog posts (all files)"
                  : "Publish as blog post"}
              </span>
              <span
                style={{
                  fontFamily: "'EB Garamond', serif",
                  fontSize: "0.92rem",
                  color: "var(--parchment-dim)",
                  lineHeight: 1.5,
                }}
              >
                {`Make ${
                  isBulk ? "each upload" : "this upload"
                } visible on `}
                <code
                  className="mono"
                  style={{ fontSize: "0.78rem", color: "var(--amber-dim)" }}
                >
                  /
                </code>
                {" and at "}
                <code
                  className="mono"
                  style={{ fontSize: "0.78rem", color: "var(--amber-dim)" }}
                >
                  /post/&lt;slug&gt;
                </code>
                {`. The Codex itself (conclusions, contradictions, review queue) stays private. You can toggle this later from the dashboard.${
                  isBulk ? " Each file gets its own post." : ""
                }`}
              </span>
            </span>
          </label>

          {publishAsPost && (
            <div
              style={{
                marginTop: "1rem",
                display: "flex",
                flexDirection: "column",
                gap: "0.8rem",
              }}
            >
              <div>
                <label
                  className="mono"
                  style={{
                    fontSize: "0.62rem",
                    letterSpacing: "0.2em",
                    textTransform: "uppercase",
                    color: "var(--amber-dim)",
                    display: "block",
                    marginBottom: "0.3rem",
                  }}
                >
                  {isBulk
                    ? "Shared excerpt (optional — same for every post)"
                    : "Excerpt (optional — shown on index card)"}
                </label>
                <textarea
                  value={blogExcerpt}
                  onChange={(e) => setBlogExcerpt(e.target.value)}
                  rows={2}
                  maxLength={400}
                  placeholder="One or two sentences that make a reader want to click in."
                />
              </div>
              <div>
                <label
                  className="mono"
                  style={{
                    fontSize: "0.62rem",
                    letterSpacing: "0.2em",
                    textTransform: "uppercase",
                    color: "var(--amber-dim)",
                    display: "block",
                    marginBottom: "0.3rem",
                  }}
                >
                  Byline (optional — defaults to your founder name)
                </label>
                <input
                  type="text"
                  value={authorBio}
                  onChange={(e) => setAuthorBio(e.target.value)}
                  maxLength={160}
                  placeholder="e.g. Host and guest, July 2026 · podcast ep. 14"
                />
              </div>
            </div>
          )}
        </div>

        {error && (
          <p style={{ color: "var(--ember)", fontSize: "0.9rem" }}>{error}</p>
        )}
        {success && (
          <p
            style={{
              color: success.startsWith("Failed")
                ? "var(--ember)"
                : "var(--success)",
              fontSize: "0.9rem",
            }}
          >
            {success}
          </p>
        )}

        <button
          type="submit"
          className="btn-solid btn"
          disabled={committing || !hasItems}
        >
          {commitLabel}
        </button>
      </form>
    </main>
  );
}
