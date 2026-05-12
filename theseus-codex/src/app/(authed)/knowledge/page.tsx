import Link from "next/link";
import TabNav from "@/components/TabNav";
import { db } from "@/lib/db";
import { founderDisplayName } from "@/lib/founderDisplay";
import { requireTenantContext } from "@/lib/tenant";
import ConclusionsPage from "../conclusions/page";
import ExplorerPage from "../explorer/page";
import LibraryPage from "../library/page";
import RetiredRouteToast from "./RetiredRouteToast";
import KnowledgePrinciplesTab from "./PrinciplesTab";
import KnowledgeCasesTab from "./CasesTab";

const KNOWLEDGE_TABS = [
  { id: "conclusions", label: "Conclusions" },
  { id: "principles", label: "Principles" },
  { id: "cases", label: "Cases" },
  { id: "explorer", label: "Explorer" },
  { id: "library", label: "Library" },
  { id: "transcripts", label: "Transcripts" },
] as const;

type KnowledgeTab = (typeof KNOWLEDGE_TABS)[number]["id"];

type KnowledgeSearchParams = {
  tab?: string;
  notice?: string;
  tier?: string;
  topic?: string;
  asOf?: string;
  q?: string;
  page?: string;
  request?: string;
  requested?: string;
  error?: string;
};

function resolveTab(raw: string | undefined): KnowledgeTab {
  return KNOWLEDGE_TABS.some((tab) => tab.id === raw)
    ? (raw as KnowledgeTab)
    : "conclusions";
}

export default async function KnowledgePage({
  searchParams,
}: {
  searchParams: Promise<KnowledgeSearchParams>;
}) {
  const sp = await searchParams;
  const activeTab = resolveTab(sp.tab);

  return (
    <>
      <RetiredRouteToast notice={sp.notice} />
      <section style={{ paddingTop: "1.25rem" }}>
        <header
          style={{
            maxWidth: "1200px",
            margin: "0 auto 0.5rem",
            padding: "0 1.5rem",
          }}
        >
          <h1
            style={{
              fontFamily: "'Cinzel', serif",
              fontSize: "1.25rem",
              letterSpacing: "0.08em",
              color: "var(--amber)",
              margin: 0,
            }}
          >
            Knowledge
          </h1>
        </header>
        <TabNav
          basePath="/knowledge"
          current={activeTab}
          tabs={KNOWLEDGE_TABS as unknown as ReadonlyArray<{ id: string; label: string }>}
        />
      </section>

      {activeTab === "conclusions" ? (
        <ConclusionsPage searchParams={Promise.resolve(sp)} />
      ) : activeTab === "principles" ? (
        <KnowledgePrinciplesTab />
      ) : activeTab === "cases" ? (
        <KnowledgeCasesTab />
      ) : activeTab === "explorer" ? (
        <ExplorerPage />
      ) : activeTab === "library" ? (
        <LibraryPage searchParams={Promise.resolve(sp)} />
      ) : (
        <TranscriptsIndex />
      )}
    </>
  );
}

const AUDIO_SOURCE_TYPES = new Set(["audio", "dialectic", "podcast", "session"]);

function transcriptSourceKind(sourceType: string): "audio" | "transcript" | "text" {
  const normalized = sourceType.trim().toLowerCase();
  if (AUDIO_SOURCE_TYPES.has(normalized)) return "audio";
  if (normalized === "transcript") return "transcript";
  return "text";
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case "ingested":
      return "badge badge-ingested";
    case "processing":
      return "badge badge-processing";
    case "failed":
      return "badge badge-failed";
    default:
      return "badge badge-pending";
  }
}

async function TranscriptsIndex() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  const uploads = await db.upload.findMany({
    where: {
      organizationId: tenant.organizationId,
      deletedAt: null,
      AND: [
        {
          OR: [
            { visibility: { not: "private" } },
            { founderId: tenant.founderId },
          ],
        },
        {
          OR: [
            { sourceType: { in: ["audio", "dialectic", "podcast", "session", "transcript"] } },
            { chunks: { some: {} } },
          ],
        },
      ],
    },
    orderBy: { createdAt: "desc" },
    take: 200,
    select: {
      id: true,
      title: true,
      sourceType: true,
      status: true,
      createdAt: true,
      blurb: true,
      description: true,
      founder: {
        select: { displayName: true, name: true, username: true },
      },
      _count: { select: { chunks: true } },
    },
  });

  return (
    <main style={{ maxWidth: "1040px", margin: "0 auto", padding: "1.5rem 1.5rem 4rem" }}>
      <header style={{ marginBottom: "1.25rem" }}>
        <h2
          style={{
            fontFamily: "'Cinzel', serif",
            color: "var(--gold)",
            letterSpacing: "0.08em",
            margin: 0,
          }}
        >
          Transcripts
        </h2>
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.9rem", lineHeight: 1.6, maxWidth: "44rem", margin: "0.35rem 0 0" }}>
          Audio, dialogue, and other uploads with a readable transcript surface and stable chunk anchors.
        </p>
      </header>

      {uploads.length === 0 ? (
        <div className="portal-card" style={{ padding: "1.25rem", color: "var(--parchment-dim)" }}>
          No transcript-indexed uploads are available yet.
        </div>
      ) : (
        <ul className="transcript-index-list">
          {uploads.map((upload) => {
            const kind = transcriptSourceKind(upload.sourceType);
            const chunkCount = upload._count.chunks;
            const hasTranscript = chunkCount > 0;
            return (
              <li key={upload.id} className="portal-card transcript-index-row">
                <div className="transcript-index-row-head">
                  <span
                    className={`mono transcript-index-kind transcript-index-kind-${kind}`}
                    aria-label={`Source type ${upload.sourceType}`}
                  >
                    {kind === "audio" ? "AUDIO" : kind === "transcript" ? "TRANSCRIPT" : "TEXT"}
                  </span>
                  <h3 className="transcript-index-title">
                    <Link href={`/transcripts/${upload.id}`}>{upload.title}</Link>
                  </h3>
                </div>
                <dl className="transcript-index-fields">
                  <div>
                    <dt className="mono">Source</dt>
                    <dd>{upload.sourceType}</dd>
                  </div>
                  <div>
                    <dt className="mono">Transcript</dt>
                    <dd>{hasTranscript ? "available" : "not chunked"}</dd>
                  </div>
                  <div>
                    <dt className="mono">Chunks</dt>
                    <dd>{chunkCount.toLocaleString()}</dd>
                  </div>
                  <div>
                    <dt className="mono">State</dt>
                    <dd>
                      <span className={statusBadgeClass(upload.status)}>{upload.status}</span>
                    </dd>
                  </div>
                  <div>
                    <dt className="mono">Created</dt>
                    <dd>{new Date(upload.createdAt).toLocaleDateString()}</dd>
                  </div>
                  <div>
                    <dt className="mono">Author</dt>
                    <dd>{founderDisplayName(upload.founder)}</dd>
                  </div>
                </dl>
                {upload.blurb || upload.description ? (
                  <p className="transcript-index-blurb">
                    {(upload.blurb || upload.description || "").slice(0, 220)}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
