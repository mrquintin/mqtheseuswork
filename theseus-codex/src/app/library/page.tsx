/**
 * /library — public-facing reading list (prompt 09).
 *
 * The Codex's proprietary surface lives elsewhere (Currents, Principles,
 * Articles, the blog index at `/`). This page is the public counterpart:
 * outside material the firm explicitly endorses, plus a collapsed
 * "studied / opposing" section so a reader can see what we engage with
 * but don't stand behind.
 *
 * Provenance is the load-bearing column. Anything proprietary is
 * filtered out — by definition that material has its own surfaces. The
 * split into ENDORSED vs STUDIED+OPPOSING is the founder's directive:
 * what we'd point to as "the way we think" goes up top; the rest is a
 * disclosure of what we read but disagree with.
 */
import Link from "next/link";

import { db } from "@/lib/db";
import PublicHeader from "@/components/PublicHeader";

export const revalidate = 300;

type LibraryRow = {
  id: string;
  title: string;
  authorBio: string | null;
  slug: string | null;
  blogExcerpt: string | null;
  provenance:
    | "PROPRIETARY"
    | "ENDORSED_EXTERNAL"
    | "STUDIED_EXTERNAL"
    | "OPPOSING_EXTERNAL";
  provenanceRationale: string | null;
  publishedAt: Date | null;
};

async function loadLibrary(): Promise<{
  endorsed: LibraryRow[];
  studied: LibraryRow[];
  opposing: LibraryRow[];
}> {
  // Public surface: only published rows, never the proprietary ones
  // (those have dedicated surfaces). We do NOT filter by org — the
  // library is a single public reading list.
  const rows = (await db.upload.findMany({
    where: {
      deletedAt: null,
      publishedAt: { not: null },
      visibility: "org",
      provenance: { in: ["ENDORSED_EXTERNAL", "STUDIED_EXTERNAL", "OPPOSING_EXTERNAL"] },
    },
    select: {
      id: true,
      title: true,
      authorBio: true,
      slug: true,
      blogExcerpt: true,
      provenance: true,
      provenanceRationale: true,
      publishedAt: true,
    },
    orderBy: { publishedAt: "desc" },
    take: 200,
  })) as LibraryRow[];

  return {
    endorsed: rows.filter((r) => r.provenance === "ENDORSED_EXTERNAL"),
    studied: rows.filter((r) => r.provenance === "STUDIED_EXTERNAL"),
    opposing: rows.filter((r) => r.provenance === "OPPOSING_EXTERNAL"),
  };
}

function LibraryEntry({ row }: { row: LibraryRow }) {
  return (
    <li
      style={{
        padding: "1rem 0",
        borderBottom: "1px solid var(--stroke)",
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--amber-dim)",
        }}
      >
        {row.provenance.replace(/_/g, " ").toLowerCase()}
      </div>
      <h3
        style={{
          fontFamily: "'EB Garamond', serif",
          fontSize: "1.2rem",
          color: "var(--parchment)",
          margin: "0.3rem 0",
        }}
      >
        {row.slug ? (
          <Link href={`/post/${row.slug}`} style={{ color: "inherit" }}>
            {row.title}
          </Link>
        ) : (
          row.title
        )}
      </h3>
      {row.authorBio && (
        <div style={{ fontSize: "0.85rem", color: "var(--parchment-dim)" }}>
          {row.authorBio}
        </div>
      )}
      {row.provenanceRationale && (
        <p
          style={{
            fontStyle: "italic",
            color: "var(--parchment-dim)",
            fontSize: "0.9rem",
            margin: "0.5rem 0 0",
          }}
        >
          Why we keep it: {row.provenanceRationale}
        </p>
      )}
    </li>
  );
}

export default async function LibraryPage() {
  const { endorsed, studied, opposing } = await loadLibrary();
  return (
    <>
      <PublicHeader authed={false} />
      <main
        style={{
          maxWidth: "780px",
          margin: "0 auto",
          padding: "3rem 1.5rem 5rem",
        }}
      >
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            letterSpacing: "0.06em",
            color: "var(--amber)",
            textShadow: "var(--glow-sm)",
            fontSize: "1.6rem",
            margin: 0,
          }}
        >
          Library
        </h1>
        <p
          style={{
            color: "var(--parchment-dim)",
            marginTop: "0.8rem",
            lineHeight: 1.65,
          }}
        >
          Outside writing the firm reads. <strong>Endorsed</strong>{" "}
          pieces represent the way we think; we'd point to them as
          ours-in-spirit. <strong>Studied</strong> and{" "}
          <strong>opposing</strong> material is kept for argument value
          — what we want to be able to reason about or argue against.
          Material the firm itself authored lives elsewhere: in Currents,
          Principles, and the article rail on the homepage.
        </p>

        <section style={{ marginTop: "2.5rem" }}>
          <h2
            className="mono"
            style={{
              fontSize: "0.7rem",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "var(--amber)",
              borderBottom: "1px solid var(--stroke)",
              paddingBottom: "0.4rem",
            }}
          >
            Endorsed — the way we think
          </h2>
          {endorsed.length === 0 ? (
            <p style={{ color: "var(--parchment-dim)", marginTop: "0.8rem" }}>
              No endorsed external sources yet.
            </p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, marginTop: "0.6rem" }}>
              {endorsed.map((row) => (
                <LibraryEntry key={row.id} row={row} />
              ))}
            </ul>
          )}
        </section>

        <details style={{ marginTop: "3rem" }}>
          <summary
            className="mono"
            style={{
              fontSize: "0.7rem",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "var(--amber-dim)",
              cursor: "pointer",
            }}
          >
            Studied & opposing ({studied.length + opposing.length})
          </summary>
          <p
            style={{
              color: "var(--parchment-dim)",
              marginTop: "0.8rem",
              fontSize: "0.9rem",
            }}
          >
            Material we read but don&apos;t endorse. The firm wants to be
            able to reason about it, argue against it, or use it as a
            test case — not adopt it.
          </p>
          {studied.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {studied.map((row) => (
                <LibraryEntry key={row.id} row={row} />
              ))}
            </ul>
          )}
          {opposing.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {opposing.map((row) => (
                <LibraryEntry key={row.id} row={row} />
              ))}
            </ul>
          )}
        </details>
      </main>
    </>
  );
}
