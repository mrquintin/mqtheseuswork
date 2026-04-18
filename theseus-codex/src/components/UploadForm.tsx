"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";

const ACCEPTED_EXTENSIONS =
  ".txt,.md,.markdown,.pdf,.docx,.vtt,.jsonl,.mp3,.m4a,.wav,.webm,.ogg";

/**
 * Upload form.
 *
 * Visual
 * ------
 * The Discobolus now lives as a half-page backdrop (see UploadPage in
 * app/(authed)/upload/page.tsx + SculptureBackdrop). This component is
 * just the form itself; the patron sculpture is the room it sits in.
 *
 * Vercel-compat copy
 * ------------------
 * Earlier copy mentioned `python -m noosphere ingest`, which is only
 * true for self-hosted deploys. Neutral phrasing here; the scribe's log
 * (polled after submit) reports the real status.
 */
export default function UploadForm() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragover, setDragover] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sourceType, setSourceType] = useState("written");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [pollLog, setPollLog] = useState("");
  // Blog publish fields — default OFF per the product spec. The
  // checkbox is the single gate; when enabled, optional excerpt
  // and byline inputs appear below it. Slug is derived server-side
  // from `title` at insert time so the founder never has to care.
  const [publishAsPost, setPublishAsPost] = useState(false);
  const [blogExcerpt, setBlogExcerpt] = useState("");
  const [authorBio, setAuthorBio] = useState("");

  const handleFile = useCallback(
    (f: File) => {
      setFile(f);
      if (!title) {
        setTitle(f.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " "));
      }
      if (f.type.startsWith("audio/")) {
        setSourceType("audio");
      }
    },
    [title],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragover(false);
      if (e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
      }
    },
    [handleFile],
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Please select a file to upload");
      return;
    }
    setError("");
    setSuccess("");
    setUploading(true);
    setPollLog("");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", title);
    formData.append("description", description);
    formData.append("sourceType", sourceType);
    // Blog publish fields. The checkbox defaults to unchecked, so an
    // unmodified upload stays a private founder artifact — we still
    // POST the "false" value explicitly so the server-side contract is
    // unambiguous.
    formData.append("publishAsPost", publishAsPost ? "1" : "0");
    if (publishAsPost) {
      formData.append("blogExcerpt", blogExcerpt.trim());
      formData.append("authorBio", authorBio.trim());
    }

    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();
    if (!res.ok) {
      setUploading(false);
      setError(data.error || "Upload failed");
      return;
    }

    setSuccess("Upload received. Noosphere is processing in the cloud…");
    const id = data.id as string;
    // Track whether a queued_offline state has persisted long enough to
    // surface a "Retry processing" affordance. The GitHub Actions cron
    // sweeps every 10 minutes; anything stuck past that warrants a
    // manual retry button.
    let queuedOfflineStart: number | null = null;

    const iv = setInterval(async () => {
      const pr = await fetch(`/api/upload/${id}`);
      const u = await pr.json();
      if (u.processLog) setPollLog(u.processLog.slice(-4000));

      // Intermediate states keep polling. `processing` is new: it means
      // the GitHub Actions workflow has been dispatched and Noosphere
      // is actively analyzing the upload.
      if (u.status === "processing") {
        setSuccess("Noosphere is analyzing this upload… (usually 1–2 minutes)");
      } else if (u.status === "queued_offline") {
        if (queuedOfflineStart === null) {
          queuedOfflineStart = Date.now();
        }
        const waitedMs = Date.now() - queuedOfflineStart;
        if (waitedMs < 60_000) {
          setSuccess(
            "Upload saved. Waiting for the cloud processor to pick it up…",
          );
        } else {
          setSuccess(
            "Processing is taking longer than usual. The cron sweep picks up " +
              "queued uploads every 10 minutes, or you can retry from /dashboard.",
          );
        }
      }

      // Terminal states — stop polling.
      if (u.status === "ingested" || u.status === "failed") {
        clearInterval(iv);
        setUploading(false);
        if (u.status === "ingested") {
          setSuccess(
            `Ingest complete — ${u.claimsCount || 0} claim(s) extracted. Redirecting…`,
          );
        } else {
          setSuccess(`Failed: ${u.errorMessage || "unknown error"}`);
        }
        setTimeout(() => router.push("/dashboard"), 2400);
      }
    }, 1500);

    // Hard stop at 10 minutes — the workflow's own timeout is 25 min but
    // the user shouldn't stare at a spinner that long. Dashboard polling
    // takes over once they navigate.
    setTimeout(() => clearInterval(iv), 600_000);
  }

  return (
    <main
      style={{
        maxWidth: "680px",
        // Offset the form to the right so it doesn't overlap the Discobolus
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
          Upload Contribution · Discobolus, MSR
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
          Commit a transcript, essay, or session. Markdown, plain text,
          WebVTT, Dialectic JSONL, PDF, DOCX, and common audio formats
          are accepted.
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
            accept={ACCEPTED_EXTENSIONS}
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files?.[0]) handleFile(e.target.files[0]);
            }}
          />

          {file ? (
            <div>
              <p
                className="mono"
                style={{
                  fontSize: "0.62rem",
                  letterSpacing: "0.3em",
                  textTransform: "uppercase",
                  color: "var(--ember)",
                  margin: 0,
                }}
              >
                Sigillatum · Sealed
              </p>
              <p
                style={{
                  fontFamily: "'EB Garamond', serif",
                  fontSize: "1.15rem",
                  color: "var(--amber)",
                  margin: "0.4rem 0 0",
                }}
              >
                {file.name}
              </p>
              <p
                className="mono"
                style={{
                  fontSize: "0.7rem",
                  letterSpacing: "0.1em",
                  color: "var(--parchment-dim)",
                  marginTop: "0.35rem",
                  marginBottom: 0,
                }}
              >
                {(file.size / 1024).toFixed(0)} KB · {file.type || "unknown type"}
              </p>
            </div>
          ) : (
            <div>
              <p
                className="mono"
                style={{
                  fontSize: "0.62rem",
                  letterSpacing: "0.3em",
                  textTransform: "uppercase",
                  color: "var(--amber-dim)",
                  margin: 0,
                }}
              >
                Liber Apertus
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
                Drop a file here, or click to browse.
              </p>
            </div>
          )}
        </div>

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
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </div>

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
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value)}
          >
            <option value="written">Written</option>
            <option value="annotation">Annotation</option>
            <option value="external">External</option>
            <option value="audio">Audio</option>
            <option value="transcript">Transcript</option>
          </select>
        </div>

        {/* ── Publication toggle ──────────────────────────────────── */}
        {/* Privacy-preserving by default: the checkbox is explicitly  */}
        {/* NOT checked on fresh render, so a hurried founder uploads  */}
        {/* private data unless they deliberately opt in. Expanded     */}
        {/* fields (excerpt + byline) only appear once the toggle is   */}
        {/* on, to keep the form quiet when nobody's publishing.       */}
        <div
          style={{
            marginTop: "0.5rem",
            padding: "1rem 1.1rem",
            border: "1px solid var(--stroke)",
            borderRadius: "4px",
            background: "rgba(212, 160, 23, 0.035)",
          }}
        >
          <label
            style={{
              display: "flex",
              gap: "0.65rem",
              alignItems: "flex-start",
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={publishAsPost}
              onChange={(e) => setPublishAsPost(e.target.checked)}
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
                Publish as blog post
              </span>
              <span
                style={{
                  fontFamily: "'EB Garamond', serif",
                  fontSize: "0.92rem",
                  color: "var(--parchment-dim)",
                  lineHeight: 1.5,
                }}
              >
                Make this upload visible on{" "}
                <code
                  className="mono"
                  style={{ fontSize: "0.78rem", color: "var(--amber-dim)" }}
                >
                  /
                </code>{" "}
                and at{" "}
                <code
                  className="mono"
                  style={{ fontSize: "0.78rem", color: "var(--amber-dim)" }}
                >
                  /post/&lt;slug&gt;
                </code>
                . The Codex itself (conclusions, contradictions, review
                queue) stays private. You can toggle this later from
                the dashboard.
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
                  Excerpt (optional — shown on index card)
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

        {error && <p style={{ color: "var(--ember)", fontSize: "0.9rem" }}>{error}</p>}
        {success && (
          <p
            style={{
              color: success.startsWith("Failed") ? "var(--ember)" : "var(--success)",
              fontSize: "0.9rem",
            }}
          >
            {success}
          </p>
        )}

        {pollLog && (
          <pre
            className="ascii-frame"
            data-label="SCRIBE'S LOG"
            style={{
              maxHeight: "240px",
              overflow: "auto",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.68rem",
              lineHeight: 1.55,
              color: "var(--parchment)",
              background:
                "linear-gradient(180deg, rgba(20,14,6,0.5) 0%, rgba(30,20,8,0.4) 100%)",
              padding: "1rem 1.25rem",
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {pollLog}
          </pre>
        )}

        <button
          type="submit"
          className="btn-solid btn"
          disabled={uploading || !file}
        >
          {uploading ? "Committing…" : "Commit to the Codex"}
        </button>
      </form>
    </main>
  );
}
