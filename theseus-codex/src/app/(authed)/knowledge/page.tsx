import Link from "next/link";
import TabNav from "@/components/TabNav";
import { db } from "@/lib/db";
import { founderDisplayName } from "@/lib/founderDisplay";
import { requireTenantContext } from "@/lib/tenant";
import ConclusionsPage from "../conclusions/page";
import ExplorerPage from "../explorer/page";
import LibraryPage from "../library/page";
import RetiredRouteToast from "./RetiredRouteToast";

const KNOWLEDGE_TABS = [
  { id: "conclusions", label: "Conclusions" },
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
      <section style={{ paddingTop: "1.5rem" }}>
        <header
          style={{
            maxWidth: "1200px",
            margin: "0 auto 1rem",
            padding: "0 1.5rem",
          }}
        >
          <h1
            style={{
              fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
              fontSize: "1.7rem",
              letterSpacing: "0.16em",
              color: "var(--amber)",
              margin: 0,
              textShadow: "var(--glow-sm)",
            }}
          >
            Knowledge
          </h1>
          <p
            className="mono"
            style={{
              color: "var(--amber-dim)",
              fontSize: "0.62rem",
              letterSpacing: "0.24em",
              margin: "0.3rem 0 0",
              textTransform: "uppercase",
            }}
          >
            Conclusions · Explorer · Library · Transcripts
          </p>
        </header>
        <TabNav
          basePath="/knowledge"
          current={activeTab}
          tabs={KNOWLEDGE_TABS as unknown as ReadonlyArray<{ id: string; label: string }>}
        />
      </section>

      {activeTab === "conclusions" ? (
        <ConclusionsPage searchParams={Promise.resolve(sp)} />
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
            { sourceType: "transcript" },
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
    <main style={{ maxWidth: "1000px", margin: "0 auto", padding: "2rem 2rem 4rem" }}>
      <header style={{ marginBottom: "1.75rem" }}>
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
        <p style={{ color: "var(--parchment-dim)", fontSize: "0.9rem", lineHeight: 1.6, maxWidth: "44rem" }}>
          Every upload with a transcript surface, including stable chunk anchors for citation and review.
        </p>
      </header>

      {uploads.length === 0 ? (
        <div className="portal-card" style={{ padding: "1.25rem", color: "var(--parchment-dim)" }}>
          No transcript-indexed uploads are available yet.
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "0.8rem" }}>
          {uploads.map((upload) => (
            <li key={upload.id} className="portal-card" style={{ padding: "1rem 1.2rem" }}>
              <Link
                href={`/transcripts/${upload.id}`}
                style={{ color: "inherit", textDecoration: "none" }}
              >
                <div
                  className="mono"
                  style={{
                    color: "var(--amber-dim)",
                    fontSize: "0.6rem",
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                  }}
                >
                  {upload.sourceType} · {upload.status} · {upload._count.chunks} chunks · {new Date(upload.createdAt).toLocaleDateString()}
                </div>
                <h3
                  style={{
                    color: "var(--parchment)",
                    fontFamily: "'EB Garamond', serif",
                    fontSize: "1.1rem",
                    margin: "0.35rem 0 0",
                  }}
                >
                  {upload.title}
                </h3>
                <p style={{ color: "var(--parchment-dim)", fontSize: "0.85rem", margin: "0.35rem 0 0" }}>
                  {founderDisplayName(upload.founder)}
                  {upload.blurb || upload.description
                    ? ` · ${(upload.blurb || upload.description || "").slice(0, 180)}`
                    : ""}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
