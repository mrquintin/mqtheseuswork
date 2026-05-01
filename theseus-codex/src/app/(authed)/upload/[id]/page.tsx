import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import PublishToToolbar from "@/components/PublishToToolbar";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { founderDisplayName } from "@/lib/founderDisplay";
import { canWrite } from "@/lib/roles";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;
type SearchParams = Promise<{ error?: string }>;

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
      founder: { select: { displayName: true, name: true, username: true } },
    },
  });
  if (!upload) notFound();

  const sp = await searchParams;
  const canPublish = canWrite(founder.role) && Boolean(upload.textContent?.trim());

  return (
    <main style={{ display: "grid", gap: "1rem", margin: "0 auto", maxWidth: 1040, padding: "1.5rem 1rem 3rem" }}>
      <header style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", justifyContent: "space-between" }}>
        <div>
          <Link className="mono" href="/knowledge?tab=library" style={{ color: "var(--amber-dim)", fontSize: "0.65rem", textDecoration: "none" }}>
            Library
          </Link>
          <h1 style={{ color: "var(--amber)", fontFamily: "'Cinzel Decorative', 'Cinzel', serif", margin: "0.25rem 0 0" }}>
            {upload.title}
          </h1>
          <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.65rem", margin: "0.35rem 0 0" }}>
            {upload.sourceType} / {upload.status} / {founderDisplayName(upload.founder)} / {new Date(upload.createdAt).toLocaleDateString()}
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

      {!upload.textContent?.trim() ? (
        <section className="portal-card" style={{ color: "var(--parchment-dim)", padding: "1rem" }}>
          This upload has no extracted text yet, so it cannot be formatted into a Substack draft.
        </section>
      ) : null}

      <section className="portal-card" style={{ display: "grid", gap: "0.65rem", padding: "1rem" }}>
        <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.64rem" }}>
          {upload.originalName} / {upload.mimeType} / {(upload.fileSize / 1024).toFixed(0)} KB / {upload.visibility}
        </div>
        {upload.description ? (
          <p style={{ color: "var(--parchment-dim)", lineHeight: 1.55, margin: 0 }}>
            {upload.description}
          </p>
        ) : null}
      </section>

      <article className="portal-card" style={{ padding: "1rem" }}>
        <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem", letterSpacing: "0.18em", margin: "0 0 0.75rem", textTransform: "uppercase" }}>
          Source text
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
          {upload.textContent || ""}
        </pre>
      </article>
    </main>
  );
}
