import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import PublishToToolbar from "@/components/PublishToToolbar";
import PublishToggle from "@/components/PublishToggle";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import {
  activeEmbeddingModelName,
  decodeFloat32Vector,
} from "@/lib/embeddingHealth";
import { founderDisplayName } from "@/lib/founderDisplay";
import { canWrite } from "@/lib/roles";

import TranscriptAnchorClient from "./TranscriptAnchorClient";

export const dynamic = "force-dynamic";

type Params = Promise<{ uploadId: string }>;
type SearchParams = Promise<{ error?: string }>;

const STOPWORDS = new Set([
  "and",
  "are",
  "but",
  "for",
  "from",
  "have",
  "into",
  "not",
  "that",
  "the",
  "their",
  "this",
  "was",
  "with",
  "would",
]);

function formatDate(value: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(value);
}

function formatTimestamp(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function excerpt(text: string | null | undefined, max = 360): string {
  const cleaned = (text || "").replace(/\s+/g, " ").trim();
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max - 3).trimEnd()}...`;
}

function tokenize(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter((token) => token.length >= 3 && !STOPWORDS.has(token)),
  );
}

function overlapScore(left: string, right: string): number {
  const a = tokenize(left);
  const b = tokenize(right);
  if (a.size === 0 || b.size === 0) return 0;
  let hits = 0;
  for (const token of b) {
    if (a.has(token)) hits++;
  }
  return hits / Math.sqrt(a.size);
}

function cosine(left: number[], right: number[]): number | null {
  if (left.length !== right.length || left.length === 0) return null;
  let dot = 0;
  let leftNorm = 0;
  let rightNorm = 0;
  for (let index = 0; index < left.length; index++) {
    dot += left[index]! * right[index]!;
    leftNorm += left[index]! * left[index]!;
    rightNorm += right[index]! * right[index]!;
  }
  if (leftNorm === 0 || rightNorm === 0) return null;
  return dot / (Math.sqrt(leftNorm) * Math.sqrt(rightNorm));
}

type SemanticChunkRow = {
  id: string;
  vector: unknown;
  dimension: number;
};

type SemanticConclusionRow = {
  id: string;
  text: string;
  confidenceTier: string;
  topicHint: string;
  rationale: string;
  vector: unknown;
  dimension: number;
};

async function semanticRelatedConclusions(organizationId: string, uploadId: string) {
  try {
    const modelName = await activeEmbeddingModelName();
    const [chunkRows, conclusionRows] = await Promise.all([
      db.$queryRaw<SemanticChunkRow[]>`
        SELECT uc.id, e.vector, e.dimension
        FROM "UploadChunk" uc
        INNER JOIN embedding e ON e.ref_claim_id = uc.id
        WHERE uc."uploadId" = ${uploadId}
          AND e.model_name = ${modelName}
      `,
      db.$queryRaw<SemanticConclusionRow[]>`
        SELECT c.id,
               c.text,
               c."confidenceTier",
               c."topicHint",
               c.rationale,
               e.vector,
               e.dimension
        FROM "Conclusion" c
        INNER JOIN embedding e ON e.ref_claim_id = c.id
        WHERE c."organizationId" = ${organizationId}
          AND e.model_name = ${modelName}
        ORDER BY c."createdAt" DESC
        LIMIT 200
      `,
    ]);
    const chunkVectors = chunkRows
      .map((row) => decodeFloat32Vector(row.vector, row.dimension))
      .filter((vector) => vector.length > 0);
    if (chunkVectors.length === 0 || conclusionRows.length === 0) return [];

    return conclusionRows
      .map((row) => {
        const conclusionVector = decodeFloat32Vector(row.vector, row.dimension);
        const score = Math.max(
          0,
          ...chunkVectors
            .map((chunkVector) => cosine(chunkVector, conclusionVector))
            .filter((value): value is number => value !== null),
        );
        return { ...row, score };
      })
      .filter((row) => row.score > 0.18)
      .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
      .slice(0, 5);
  } catch {
    return [];
  }
}

async function relatedConclusions(organizationId: string, transcriptText: string, uploadId: string) {
  const semantic = await semanticRelatedConclusions(organizationId, uploadId);
  if (semantic.length > 0) return semantic;

  const rows = await db.conclusion.findMany({
    where: { organizationId },
    orderBy: { createdAt: "desc" },
    take: 120,
    select: {
      id: true,
      text: true,
      confidenceTier: true,
      topicHint: true,
      rationale: true,
    },
  });

  return rows
    .map((row) => ({
      ...row,
      score: overlapScore(row.text + " " + row.rationale + " " + row.topicHint, transcriptText),
    }))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
    .slice(0, 5);
}

function sectionHeading(chunks: { id: string; headingHint: string | null }[]) {
  return chunks.filter((chunk) => chunk.headingHint?.trim()).map((chunk) => ({
    id: chunk.id,
    anchor: `chunk-${chunk.id}`,
    label: chunk.headingHint!.trim(),
  }));
}

export default async function TranscriptPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const founder = await getFounder();
  if (!founder) redirect("/login");

  const { uploadId } = await params;
  const upload = await db.upload.findFirst({
    where: {
      id: uploadId,
      organizationId: founder.organizationId,
      deletedAt: null,
      OR: [{ visibility: { not: "private" } }, { founderId: founder.id }],
    },
    select: {
      id: true,
      title: true,
      description: true,
      sourceType: true,
      status: true,
      textContent: true,
      blurb: true,
      publishedAt: true,
      slug: true,
      visibility: true,
      createdAt: true,
      founderId: true,
      founder: { select: { displayName: true, name: true, username: true } },
      chunks: {
        orderBy: { index: "asc" },
        select: {
          id: true,
          index: true,
          text: true,
          startMs: true,
          endMs: true,
          speakerLabel: true,
          headingHint: true,
        },
      },
    },
  });
  if (!upload) notFound();

  const sp = await searchParams;
  const transcriptText =
    upload.chunks.map((chunk) => chunk.text).join("\n\n") || upload.textContent || "";
  const headings = sectionHeading(upload.chunks);
  const related = await relatedConclusions(founder.organizationId, transcriptText, upload.id);
  const writer = canWrite(founder.role);
  const canPublish = writer && Boolean(transcriptText.trim());
  const canTogglePublic = writer && (founder.role === "admin" || founder.id === upload.founderId);
  const blurb = upload.blurb?.trim() || upload.description?.trim() || excerpt(transcriptText, 520);

  return (
    <main className="transcript-shell">
      <TranscriptAnchorClient />
      <header className="transcript-header">
        <div>
          <Link className="mono transcript-backlink" href={`/upload/${upload.id}`}>
            Upload source
          </Link>
          <h1>{upload.title}</h1>
          <p className="mono transcript-meta">
            {founderDisplayName(upload.founder)} / {formatDate(upload.createdAt)} / Source: {upload.sourceType} / {upload.status}
          </p>
        </div>
        <div className="transcript-toolbar">
          <PublishToToolbar artifactId={upload.id} artifactType="upload" disabled={!canPublish} />
          {canTogglePublic ? (
            <div className="transcript-public-toggle">
              <span className="mono">{upload.publishedAt ? "Public" : "Private"}</span>
              <PublishToggle
                uploadId={upload.id}
                initialPublishedAt={upload.publishedAt}
                initialSlug={upload.slug}
              />
            </div>
          ) : null}
        </div>
      </header>

      {sp.error ? (
        <p role="alert" style={{ color: "var(--ember)", margin: 0 }}>
          Publish draft failed: {sp.error}
        </p>
      ) : null}

      <section className="portal-card transcript-blurb-card" aria-labelledby="transcript-blurb-title">
        <h2 className="mono" id="transcript-blurb-title">
          Blurb
        </h2>
        <p>{blurb || "No blurb has been generated for this upload yet."}</p>
        {headings.length > 0 ? (
          <nav className="transcript-chip-row" aria-label="Transcript sections">
            {headings.map((heading) => (
              <a
                className="transcript-chip"
                href={`/transcripts/${encodeURIComponent(upload.id)}?anchor=${encodeURIComponent(heading.anchor)}`}
                key={heading.anchor}
              >
                {heading.label}
              </a>
            ))}
          </nav>
        ) : null}
      </section>

      <div className="transcript-grid">
        <article className="transcript-main" aria-label="Raw transcript">
          {upload.chunks.length > 0 ? (
            upload.chunks.map((chunk) => {
              const anchor = `chunk-${chunk.id}`;
              return (
                <section
                  className="transcript-chunk"
                  data-testid={`transcript-chunk-${chunk.id}`}
                  id={anchor}
                  key={chunk.id}
                >
                  <div className="transcript-chunk-grid">
                    <div className="transcript-time-slot">
                      {chunk.startMs !== null ? (
                        <a
                          className="mono transcript-time"
                          href={`/transcripts/${encodeURIComponent(upload.id)}?anchor=${encodeURIComponent(anchor)}`}
                        >
                          [{formatTimestamp(chunk.startMs)}]
                        </a>
                      ) : null}
                    </div>
                    <p className="transcript-body">
                      {chunk.speakerLabel ? (
                        <strong className="transcript-speaker">{chunk.speakerLabel}: </strong>
                      ) : null}
                      {chunk.text}
                    </p>
                  </div>
                </section>
              );
            })
          ) : (
            <section className="portal-card transcript-empty">
              This upload has no persisted transcript chunks yet. Re-run ingestion to create stable line anchors.
            </section>
          )}
        </article>

        <aside className="portal-card transcript-related-rail" aria-label="What the firm thinks about this">
          <RelatedPanel related={related} />
        </aside>
      </div>

      <details className="portal-card transcript-related-drawer">
        <summary className="mono">What the firm thinks about this</summary>
        <RelatedPanel related={related} />
      </details>
    </main>
  );
}

function RelatedPanel({
  related,
}: {
  related: Awaited<ReturnType<typeof relatedConclusions>>;
}) {
  return (
    <div className="transcript-related-panel">
      <h2 className="mono">What the firm thinks about this</h2>
      {related.length > 0 ? (
        <div className="transcript-related-list">
          {related.map((item) => (
            <Link className="transcript-related-card" href={`/conclusions/${item.id}`} key={item.id}>
              <span className="mono">[C:{item.id.slice(0, 8)}] / {item.confidenceTier}</span>
              <strong>{item.text}</strong>
              {item.topicHint ? <em>{item.topicHint}</em> : null}
            </Link>
          ))}
        </div>
      ) : (
        <p className="transcript-related-empty">
          No overlapping firm conclusions were found. This panel falls back to keyword overlap when embeddings are unavailable.
        </p>
      )}
    </div>
  );
}
