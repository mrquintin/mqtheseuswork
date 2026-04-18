"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import SculptureAscii from "./SculptureAsciiClient";

const ACCEPTED_EXTENSIONS =
  ".txt,.md,.markdown,.pdf,.docx,.vtt,.jsonl,.mp3,.m4a,.wav,.webm,.ogg";

/**
 * Upload form.
 *
 * Visual
 * ------
 * Previously this page had a procedural ASCII "scroll" banner which was
 * clever but didn't read convincingly as a scroll. Replaced with the
 * second Discobolus scan (MSR variant) rotating in amber — a figure mid-
 * release, a direct visual echo of what the user is about to do (commit
 * a contribution). Latin tagline "Disce, iace" — learn, then throw.
 *
 * The dropzone below is a clean ascii-frame box, no ASCII art behind the
 * text; Liber Apertus / Sigillatum typography does the ceremony.
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

    setSuccess("Upload received. Processing…");
    const id = data.id as string;

    const iv = setInterval(async () => {
      const pr = await fetch(`/api/upload/${id}`);
      const u = await pr.json();
      if (u.processLog) setPollLog(u.processLog.slice(-4000));
      if (
        u.status === "ingested" ||
        u.status === "failed" ||
        u.status === "queued_offline"
      ) {
        clearInterval(iv);
        setUploading(false);
        if (u.status === "ingested") {
          setSuccess("Ingest complete.");
        } else if (u.status === "queued_offline") {
          setSuccess(
            "Upload saved. Noosphere processing is queued — run `noosphere ingest` locally to finish.",
          );
        } else {
          setSuccess(`Failed: ${u.errorMessage || ""}`);
        }
        setTimeout(() => router.push("/dashboard"), 2200);
      }
    }, 1200);

    setTimeout(() => clearInterval(iv), 600_000);
  }

  return (
    <main
      style={{
        maxWidth: "820px",
        margin: "0 auto",
        padding: "2rem 2rem 3rem",
      }}
    >
      {/* ── Discobolus banner ────────────────────────────────────────────
          The second (MSR) Discobolus scan, rotating. A figure poised
          between preparation and release is the exact shape of the
          action the user is about to take on this page. */}
      <section
        aria-hidden="true"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "2rem",
          flexWrap: "wrap",
          marginBottom: "2rem",
        }}
      >
        <SculptureAscii
          src="/sculptures/discobolus-alt.mesh.bin"
          cols={44}
          rows={24}
          yawSpeed={0.04}
          pitch={-0.08}
          ariaLabel="Discobolus — the discus thrower, rotating as amber ASCII"
        />
        <div style={{ maxWidth: "320px" }}>
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
            }}
          >
            Commit a transcript, essay, or session. Markdown, plain text,
            WebVTT, Dialectic JSONL, PDF, DOCX, and common audio formats
            are accepted.
          </p>
        </div>
      </section>

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
