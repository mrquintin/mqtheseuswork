import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import PublishToToolbar from "@/components/PublishToToolbar";
import UploadRetryButton from "@/components/UploadRetryButton";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { founderDisplayName } from "@/lib/founderDisplay";
import { canWrite } from "@/lib/roles";
import { normalizeStatus, STATUS_LABEL } from "@/lib/uploadStatus";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;
type SearchParams = Promise<{ error?: string }>;

type StageState = "done" | "active" | "pending" | "failed" | "skipped";

function stageColor(state: StageState): string {
  switch (state) {
    case "done":
      return "var(--success)";
    case "active":
      return "var(--info, var(--amber))";
    case "failed":
      return "var(--ember)";
    case "skipped":
      return "var(--parchment-dim)";
    default:
      return "var(--parchment-dim)";
  }
}

function stageGlyph(state: StageState): string {
  switch (state) {
    case "done":
      return "✓";
    case "active":
      return "…";
    case "failed":
      return "✗";
    case "skipped":
      return "–";
    default:
      return "·";
  }
}

export default async function UploadDetailPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const founder = await getFounder();
  if (!founder) redirect("/login");

  const { id } = await params;
  const upload = await db.upload.findFirst({
    where: {
      id,
      organizationId: founder.organizationId,
      deletedAt: null,
      OR: [{ visibility: { not: "private" } }, { founderId: founder.id }],
    },
    select: {
      id: true,
      title: true,
      description: true,
      originalName: true,
      sourceType: true,
      mimeType: true,
      fileSize: true,
      status: true,
      textContent: true,
      visibility: true,
      createdAt: true,
      updatedAt: true,
      founderId: true,
      claimsCount: true,
      methodCount: true,
      substCount: true,
      principleCount: true,
      errorMessage: true,
      extractionMethod: true,
      processLog: true,
      publishedAt: true,
      slug: true,
      founder: { select: { displayName: true, name: true, username: true } },
      chunks: {
        orderBy: { index: "asc" },
        select: { id: true, index: true, text: true, startMs: true },
      },
    },
  });
  if (!upload) notFound();

  const [conclusionCount, embeddedConclusionCount] = await Promise.all([
    db.conclusion.count({
      where: {
        organizationId: founder.organizationId,
        sources: { some: { uploadId: upload.id } },
      },
    }),
    db.conclusion.count({
      where: {
        organizationId: founder.organizationId,
        embeddingJson: { not: null },
        sources: { some: { uploadId: upload.id } },
      },
    }),
  ]);

  const sp = await searchParams;
  const chunkCount = upload.chunks.length;
  const analyzedText =
    upload.chunks.map((chunk) => chunk.text).join("\n\n").trim() ||
    upload.textContent?.trim() ||
    "";
  const rawText = upload.textContent?.trim() || "";
  const rawDiffers = Boolean(rawText && analyzedText && rawText !== analyzedText);
  const hasTranscriptSurface = chunkCount > 0 || Boolean(rawText);
  const isAudio = upload.sourceType === "audio" || upload.mimeType.startsWith("audio/");
  const hasTimedChunks = upload.chunks.some((c) => c.startMs != null);
  const status = normalizeStatus(upload.status);
  const isOwner = upload.founderId === founder.id;
  const showDiagnostics = isOwner || founder.role === "admin";

  const analysisFailed = status === "failed" && hasTranscriptSurface;
  const fullyFailed = status === "failed" && !hasTranscriptSurface;

  // ── Pipeline-stage derivation ────────────────────────────────────────
  // The upload pipeline runs sequentially:
  //   received → extraction → (transcription if audio) → noosphere
  //   analysis → embeddings → publication.
  // Each stage's state is derived from durable fields on the row; we
  // never invent success. A stage is "active" only when the upload is
  // not in a terminal state and the prior stage is done.
  const receivedStage: StageState = "done";

  const hasExtractedText = Boolean(rawText) || chunkCount > 0;
  const extractionStage: StageState = hasExtractedText
    ? "done"
    : status === "failed"
      ? "failed"
      : status === "extracting" || status === "pending"
        ? "active"
        : "pending";

  const transcriptionStage: StageState = !isAudio
    ? "skipped"
    : hasTimedChunks || (isAudio && chunkCount > 0)
      ? "done"
      : status === "failed" && !hasTranscriptSurface
        ? "failed"
        : status === "extracting" || status === "pending"
          ? "active"
          : "pending";

  const analysisStage: StageState =
    status === "ingested"
      ? "done"
      : analysisFailed
        ? "failed"
        : status === "processing" || status === "awaiting_ingest"
          ? "active"
          : hasExtractedText
            ? "pending"
            : "pending";

  const embeddingStage: StageState =
    conclusionCount === 0 && status === "ingested"
      ? "skipped"
      : embeddedConclusionCount > 0 && embeddedConclusionCount === conclusionCount
        ? "done"
        : embeddedConclusionCount > 0
          ? "active"
          : status === "ingested" && conclusionCount > 0
            ? "active"
            : "pending";

  const publicationStage: StageState = upload.publishedAt
    ? "done"
    : upload.visibility !== "org"
      ? "skipped"
      : status === "ingested"
        ? "pending"
        : "pending";

  const stages: Array<{
    key: string;
    label: string;
    state: StageState;
    detail: string;
  }> = [
    {
      key: "received",
      label: "File received",
      state: receivedStage,
      detail: `${(upload.fileSize / 1024).toFixed(0)} KB · ${upload.mimeType}`,
    },
    {
      key: "extraction",
      label: isAudio ? "Audio decode" : "Text extraction",
      state: extractionStage,
      detail: extractionStage === "done"
        ? upload.extractionMethod
          ? `via ${upload.extractionMethod}`
          : "text ready"
        : extractionStage === "failed"
          ? "extractor reported failure"
          : extractionStage === "active"
            ? "running"
            : "queued",
    },
    {
      key: "transcription",
      label: "Transcription",
      state: transcriptionStage,
      detail: transcriptionStage === "skipped"
        ? "not an audio source"
        : transcriptionStage === "done"
          ? `${chunkCount} segment${chunkCount === 1 ? "" : "s"}`
          : transcriptionStage === "failed"
            ? "no transcript produced"
            : transcriptionStage === "active"
              ? "running"
              : "queued",
    },
    {
      key: "analysis",
      label: "Noosphere analysis",
      state: analysisStage,
      detail: analysisStage === "done"
        ? `${upload.claimsCount ?? 0} claim${upload.claimsCount === 1 ? "" : "s"} · ${upload.methodCount ?? 0} method · ${upload.substCount ?? 0} subst · ${upload.principleCount ?? 0} principle`
        : analysisStage === "failed"
          ? "transcript ready; downstream extraction failed"
          : analysisStage === "active"
            ? STATUS_LABEL[status]
            : "queued",
    },
    {
      key: "embeddings",
      label: "Embeddings",
      state: embeddingStage,
      detail: conclusionCount === 0
        ? status === "ingested"
          ? "no conclusions produced"
          : "awaits analysis"
        : `${embeddedConclusionCount} / ${conclusionCount} conclusions embedded`,
    },
    {
      key: "publication",
      label: "Publication",
      state: publicationStage,
      detail: upload.publishedAt && upload.slug
        ? `published to /post/${upload.slug}`
        : upload.visibility === "private"
          ? "private — not eligible"
          : upload.visibility === "semi-private"
            ? "semi-private — not eligible for public blog"
            : status === "ingested"
              ? "eligible — not published"
              : "awaits ingest",
    },
  ];

  const canPublish = canWrite(founder.role) && Boolean(analyzedText);
  const canRetry = canWrite(founder.role) && status === "failed" && isOwner;

  return (
    <main style={{ display: "grid", gap: "1rem", margin: "0 auto", maxWidth: 1040, padding: "1.5rem 1rem 3rem" }}>
      <header style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", justifyContent: "space-between" }}>
        <div>
          <Link className="mono" href="/knowledge?tab=library" style={{ color: "var(--amber-dim)", fontSize: "0.65rem", textDecoration: "none" }}>
            ← Library
          </Link>
          <h1 style={{ color: "var(--amber)", fontFamily: "'Cinzel', serif", margin: "0.25rem 0 0", fontSize: "1.4rem", letterSpacing: "0.04em" }}>
            {upload.title}
          </h1>
          <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.65rem", margin: "0.35rem 0 0" }}>
            {upload.sourceType} · {founderDisplayName(upload.founder)} · {new Date(upload.createdAt).toLocaleDateString()} · {upload.visibility}
          </p>
          <p
            className="mono"
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.4rem",
              alignItems: "center",
              margin: "0.5rem 0 0",
            }}
          >
            <span
              className={`badge ${
                status === "ingested"
                  ? "badge-ingested"
                  : status === "failed"
                    ? analysisFailed
                      ? "badge-ingested"
                      : "badge-failed"
                    : status === "pending"
                      ? "badge-pending"
                      : "badge-processing"
              }`}
            >
              {analysisFailed ? "transcript ready" : STATUS_LABEL[status]}
            </span>
            {analysisFailed ? (
              <span className="badge badge-failed">analysis failed</span>
            ) : null}
            {hasTranscriptSurface ? (
              <span style={{ color: "var(--parchment-dim)", fontSize: "0.6rem", letterSpacing: "0.14em" }}>
                {chunkCount > 0 ? `${chunkCount} chunks` : "extracted text only"}
              </span>
            ) : null}
          </p>
        </div>
        <PublishToToolbar
          artifactId={upload.id}
          artifactType="upload"
          disabled={!canPublish}
        />
      </header>

      {sp.error ? (
        <p role="alert" style={{ color: "var(--ember)", margin: 0 }}>
          Publish draft failed: {sp.error}
        </p>
      ) : null}

      {/* ── Pipeline status ─────────────────────────────────────────────── */}
      <section
        className="portal-card"
        style={{ padding: "1rem 1.1rem", display: "grid", gap: "0.55rem" }}
        aria-label="Processing pipeline"
      >
        <div
          className="mono"
          style={{
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.2em",
            textTransform: "uppercase",
          }}
        >
          Pipeline
        </div>
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "grid",
            gap: "0.4rem",
          }}
        >
          {stages.map((s) => (
            <li
              key={s.key}
              style={{
                display: "grid",
                gridTemplateColumns: "1.4rem 11rem 1fr",
                alignItems: "baseline",
                gap: "0.65rem",
                opacity: s.state === "skipped" ? 0.55 : 1,
              }}
            >
              <span
                aria-hidden
                style={{
                  color: stageColor(s.state),
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "0.9rem",
                  textAlign: "center",
                }}
              >
                {stageGlyph(s.state)}
              </span>
              <span
                style={{
                  color: "var(--parchment)",
                  fontSize: "0.9rem",
                }}
              >
                {s.label}
              </span>
              <span
                className="mono"
                style={{
                  color:
                    s.state === "failed"
                      ? "var(--ember)"
                      : "var(--parchment-dim)",
                  fontSize: "0.72rem",
                  letterSpacing: "0.04em",
                }}
              >
                {s.detail}
              </span>
            </li>
          ))}
        </ul>

        {(canRetry || (status === "pending" && isOwner)) && (
          <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap", marginTop: "0.4rem" }}>
            {canRetry ? <UploadRetryButton uploadId={upload.id} /> : null}
            {status === "pending" && isOwner ? (
              <span
                className="mono"
                style={{
                  fontSize: "0.7rem",
                  color: "var(--parchment-dim)",
                  letterSpacing: "0.08em",
                }}
              >
                Queued — the noosphere worker picks pending rows up on its
                next cycle (every ~10 min). If this row sits in pending
                much longer, the worker may not be running.
              </span>
            ) : null}
          </div>
        )}

        {analysisFailed ? (
          <p style={{ color: "var(--ember)", margin: "0.4rem 0 0", fontSize: "0.85rem", lineHeight: 1.5 }}>
            Transcript is readable below. Downstream Noosphere analysis
            failed; retry to recover methodology profiles and conclusions.
          </p>
        ) : null}

        {fullyFailed ? (
          <p style={{ color: "var(--ember)", margin: "0.4rem 0 0", fontSize: "0.85rem", lineHeight: 1.5 }}>
            Extraction failed; no transcript or text was produced. Retry,
            or re-upload if the source file was corrupted.
          </p>
        ) : null}

        {upload.errorMessage ? (
          <pre
            style={{
              margin: "0.4rem 0 0",
              padding: "0.55rem 0.7rem",
              background: "rgba(179,58,42,0.08)",
              border: "1px solid var(--ember)",
              borderRadius: 2,
              color: "var(--ember)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.74rem",
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
              overflowX: "auto",
            }}
          >
            {upload.errorMessage}
          </pre>
        ) : null}
      </section>

      {/* ── Source metadata + transcript link ───────────────────────────── */}
      <section className="portal-card" style={{ display: "grid", gap: "0.6rem", padding: "1rem 1.1rem" }}>
        <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.64rem", letterSpacing: "0.04em" }}>
          {upload.originalName}
        </div>
        {upload.description ? (
          <p style={{ color: "var(--parchment-dim)", lineHeight: 1.55, margin: 0, fontSize: "0.92rem" }}>
            {upload.description}
          </p>
        ) : null}
        {hasTranscriptSurface ? (
          <Link
            className="mono"
            href={`/transcripts/${upload.id}`}
            style={{
              color: "var(--gold, var(--amber))",
              fontSize: "0.72rem",
              textDecoration: "none",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
            }}
          >
            Open transcript → {chunkCount > 0 ? `${chunkCount} chunks` : "raw text"}
          </Link>
        ) : null}
        {upload.publishedAt && upload.slug ? (
          <Link
            className="mono"
            href={`/post/${upload.slug}`}
            style={{
              color: "var(--gold, var(--amber))",
              fontSize: "0.72rem",
              textDecoration: "none",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
            }}
          >
            View public post → /post/{upload.slug}
          </Link>
        ) : null}
      </section>

      {/* ── Body text ─────────────────────────────────────────────────── */}
      {!analyzedText && !fullyFailed ? (
        <section className="portal-card" style={{ color: "var(--parchment-dim)", padding: "1rem", fontSize: "0.9rem" }}>
          No extracted text yet. This row cannot be formatted into a
          Substack draft until extraction completes.
        </section>
      ) : null}

      {analyzedText ? (
        <article className="portal-card" style={{ padding: "1rem 1.1rem" }}>
          <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem", letterSpacing: "0.18em", margin: "0 0 0.75rem", textTransform: "uppercase" }}>
            Analyzed text
          </p>
          <pre
            style={{
              color: "var(--parchment)",
              fontFamily: "inherit",
              lineHeight: 1.55,
              margin: 0,
              overflowX: "auto",
              whiteSpace: "pre-wrap",
            }}
          >
            {analyzedText}
          </pre>
        </article>
      ) : null}

      {rawDiffers ? (
        <details className="portal-card" style={{ padding: "1rem 1.1rem" }}>
          <summary className="mono" style={{ color: "var(--amber-dim)", cursor: "pointer", fontSize: "0.62rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
            Raw extracted text
          </summary>
          <pre
            style={{
              color: "var(--parchment-dim)",
              fontFamily: "inherit",
              lineHeight: 1.55,
              margin: "0.85rem 0 0",
              overflowX: "auto",
              whiteSpace: "pre-wrap",
            }}
          >
            {rawText}
          </pre>
        </details>
      ) : null}

      {/* ── Operator diagnostics ──────────────────────────────────────── */}
      {showDiagnostics && upload.processLog && upload.processLog.trim() ? (
        <details className="portal-card" style={{ padding: "1rem 1.1rem" }}>
          <summary className="mono" style={{ color: "var(--amber-dim)", cursor: "pointer", fontSize: "0.62rem", letterSpacing: "0.18em", textTransform: "uppercase" }}>
            Process log (operator)
          </summary>
          <pre
            style={{
              color: "var(--parchment-dim)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.72rem",
              lineHeight: 1.5,
              margin: "0.85rem 0 0",
              overflowX: "auto",
              whiteSpace: "pre-wrap",
            }}
          >
            {upload.processLog}
          </pre>
        </details>
      ) : null}
    </main>
  );
}
