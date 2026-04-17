"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";

const ACCEPTED_EXTENSIONS = ".txt,.md,.markdown,.pdf,.docx,.vtt,.jsonl,.mp3,.m4a,.wav,.webm,.ogg";

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
      if (u.status === "ingested" || u.status === "failed") {
        clearInterval(iv);
        setUploading(false);
        setSuccess(u.status === "ingested" ? "Ingest complete." : `Failed: ${u.errorMessage || ""}`);
        setTimeout(() => router.push("/dashboard"), 1800);
      }
    }, 1200);

    setTimeout(() => clearInterval(iv), 600_000);
  }

  return (
    <main style={{ maxWidth: "700px", margin: "0 auto", padding: "3rem 2rem" }}>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          fontSize: "1.3rem",
          letterSpacing: "0.1em",
          color: "var(--gold)",
          marginBottom: "0.5rem",
        }}
      >
        Upload Contribution
      </h1>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontSize: "1rem",
          color: "var(--parchment-dim)",
          marginBottom: "2rem",
        }}
      >
        Accepted: Markdown, plain text, WebVTT, dialectic JSONL, PDF, DOCX, and common audio formats.
        Files are stored outside <code>public/</code> and piped through{" "}
        <code>python -m noosphere ingest</code> then <code>synthesize</code>.
      </p>

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        <div
          className={`upload-zone ${dragover ? "dragover" : ""}`}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragover(true);
          }}
          onDragLeave={() => setDragover(false)}
          onDrop={handleDrop}
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
              <p style={{ fontFamily: "'EB Garamond', serif", fontSize: "1.1rem", color: "var(--gold)" }}>
                {file.name}
              </p>
              <p
                style={{
                  fontFamily: "'Inter', sans-serif",
                  fontSize: "0.75rem",
                  color: "var(--parchment-dim)",
                  marginTop: "0.3rem",
                }}
              >
                {(file.size / 1024).toFixed(0)} KB · {file.type || "unknown type"}
              </p>
            </div>
          ) : (
            <div>
              <p style={{ fontFamily: "'EB Garamond', serif", fontSize: "1.1rem", color: "var(--parchment-dim)" }}>
                Drop a file here, or click to browse
              </p>
            </div>
          )}
        </div>

        <div>
          <label
            style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: "0.7rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              display: "block",
              marginBottom: "0.4rem",
            }}
          >
            Title
          </label>
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} required />
        </div>

        <div>
          <label
            style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: "0.7rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
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
            style={{
              fontFamily: "'Inter', sans-serif",
              fontSize: "0.7rem",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--parchment-dim)",
              display: "block",
              marginBottom: "0.4rem",
            }}
          >
            Type
          </label>
          <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
            <option value="written">Written</option>
            <option value="annotation">Annotation</option>
            <option value="external">External</option>
            <option value="audio">Audio</option>
            <option value="transcript">Transcript</option>
          </select>
        </div>

        {error && <p style={{ color: "var(--ember)", fontSize: "0.9rem" }}>{error}</p>}
        {success && <p style={{ color: "var(--success)", fontSize: "0.9rem" }}>{success}</p>}

        {pollLog && (
          <pre
            style={{
              maxHeight: "200px",
              overflow: "auto",
              fontSize: "0.65rem",
              background: "#0d0d12",
              padding: "0.75rem",
              borderRadius: "6px",
              color: "#b8b8c8",
            }}
          >
            {pollLog}
          </pre>
        )}

        <button type="submit" className="btn-solid btn" disabled={uploading || !file}>
          {uploading ? "Processing…" : "Upload & Ingest"}
        </button>
      </form>
    </main>
  );
}
