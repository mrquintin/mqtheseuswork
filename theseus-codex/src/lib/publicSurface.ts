/**
 * Public surfacing — homepage data sources.
 *
 * Single library that the public homepage (`src/app/page.tsx`) and its
 * rails consume. Each surface item type (article, conclusion, currents)
 * has exactly one server-side lister here. The contract is documented
 * in `docs/operator/public_surfacing.md`.
 *
 * Goal: every published article and every published conclusion appears
 * on `/` within 60 seconds of publication. We do not rely on a long
 * static cache. The homepage page is `force-dynamic`, and every
 * publish path calls `revalidatePath('/')` + the matching tag below.
 */

import {
  listPublishedArticles,
  resolvePublicOrganizationId,
  type PublishedConclusion,
} from "@/lib/conclusionsRead";
import { founderDisplayName } from "@/lib/founderDisplay";

// ── Cache tags ────────────────────────────────────────────────────────
// The publish actions that flip "is public" call `revalidateTag()` with
// these strings. Keep them in lockstep with the corresponding column in
// `docs/operator/public_surfacing.md`. Adding a new tag here without
// adding an invalidator at every publish path is a regression.

export const PUBLIC_HOME_ARTICLES_TAG = "public-home-articles";
export const PUBLIC_HOME_CONCLUSIONS_TAG = "public-home-conclusions";
export const PUBLIC_HOME_CURRENTS_TAG = "public-home-currents";

// ── Empty-state copy ──────────────────────────────────────────────────
// One-line hints shown when a rail has zero rows. These are snapshotted
// in `__tests__/publicSurface.test.tsx` so nobody can accidentally
// surface "undefined" or an empty box again (the bug prompt 52 fixed).

export const ARTICLES_EMPTY_COPY =
  "Long-form articles will appear here once the firm publishes them.";
export const CONCLUSIONS_EMPTY_COPY =
  "Reviewed conclusions will appear here once the firm publishes them.";
export const CURRENTS_EMPTY_COPY =
  "Live opinions will appear here once events cross the firm's significance floor.";

// ── Shared shapes ─────────────────────────────────────────────────────

export type HomeArticleCard = {
  id: string;
  href: string;
  title: string;
  subtitle: string;
  publishedAt: string;
  authorDisplayName: string;
  readingTimeMin: number;
  source: "upload" | "conclusion";
};

export type HomeConclusionCard = {
  id: string;
  href: string;
  title: string;
  subtitle: string;
  publishedAt: string;
  version: number;
};

// ── Helpers ───────────────────────────────────────────────────────────

const WORDS_PER_MINUTE = 220;

export function readingTimeMinutes(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  if (words === 0) return 1;
  return Math.max(1, Math.ceil(words / WORDS_PER_MINUTE));
}

function deriveSubtitle(text: string, limit = 180): string {
  const cleaned = text.replace(/[#>*_`-]/g, " ").replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  if (cleaned.length <= limit) return cleaned;
  const cut = cleaned.slice(0, limit);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > limit * 0.65 ? cut.slice(0, lastSpace) : cut) + "…";
}

function toIsoString(value: Date | string | null | undefined): string {
  if (!value) return "";
  if (value instanceof Date) return value.toISOString();
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString();
}

async function loadDb() {
  const { db } = await import("@/lib/db");
  return db;
}

function shouldLogOptionalDbError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return !message.includes("DATABASE_URL must be set");
}

// Ordering rule: latest first (publishedAt DESC) with id ASC for
// tie-break so two near-simultaneous publishes don't flip on refresh.
function compareCardsByPublishedAtDesc<T extends { id: string; publishedAt: string }>(a: T, b: T): number {
  if (a.publishedAt === b.publishedAt) return a.id < b.id ? -1 : 1;
  return a.publishedAt < b.publishedAt ? 1 : -1;
}

// ── Articles rail ─────────────────────────────────────────────────────

type UploadArticleRow = {
  id: string;
  slug: string | null;
  title: string;
  blogExcerpt: string | null;
  description: string | null;
  textContent: string | null;
  authorBio: string | null;
  publishedAt: Date | string | null;
  founder: {
    displayName: string | null;
    name: string | null;
    username: string | null;
  } | null;
};

async function listUploadArticles(
  organizationId: string,
  limit: number,
): Promise<HomeArticleCard[]> {
  try {
    const db = await loadDb();
    const rows = (await db.upload.findMany({
      where: {
        organizationId,
        publishedAt: { not: null },
        deletedAt: null,
        visibility: "org",
        slug: { not: null },
      },
      orderBy: [{ publishedAt: "desc" }, { id: "asc" }],
      take: limit,
      select: {
        id: true,
        slug: true,
        title: true,
        blogExcerpt: true,
        description: true,
        textContent: true,
        authorBio: true,
        publishedAt: true,
        founder: { select: { displayName: true, name: true, username: true } },
      },
    })) as unknown as UploadArticleRow[];

    return rows.flatMap((row): HomeArticleCard[] => {
      if (!row.slug || !row.publishedAt) return [];
      const subtitleSource =
        row.blogExcerpt || row.description || row.textContent || "";
      const readingSource = row.textContent || row.description || "";
      const authorDisplayName =
        row.authorBio?.trim() ||
        founderDisplayName({
          displayName: row.founder?.displayName ?? null,
          name: row.founder?.name ?? null,
          username: row.founder?.username ?? null,
        });
      return [
        {
          id: row.id,
          href: `/post/${encodeURIComponent(row.slug)}`,
          title: row.title,
          subtitle: deriveSubtitle(subtitleSource),
          publishedAt: toIsoString(row.publishedAt),
          authorDisplayName,
          readingTimeMin: readingTimeMinutes(readingSource),
          source: "upload",
        },
      ];
    });
  } catch (error) {
    if (shouldLogOptionalDbError(error)) {
      console.error("[publicSurface] upload article query failed:", error);
    }
    return [];
  }
}

type ConclusionFounderRow = {
  id: string;
  attributedFounder: {
    displayName: string | null;
    name: string | null;
    username: string | null;
  } | null;
};

async function authorByConclusionId(
  organizationId: string,
  sourceConclusionIds: string[],
): Promise<Map<string, string>> {
  if (sourceConclusionIds.length === 0) return new Map();
  try {
    const db = await loadDb();
    const rows = (await db.conclusion.findMany({
      where: { organizationId, id: { in: sourceConclusionIds } },
      select: {
        id: true,
        attributedFounder: {
          select: { displayName: true, name: true, username: true },
        },
      },
    })) as unknown as ConclusionFounderRow[];
    const result = new Map<string, string>();
    for (const row of rows) {
      result.set(
        row.id,
        founderDisplayName({
          displayName: row.attributedFounder?.displayName ?? null,
          name: row.attributedFounder?.name ?? null,
          username: row.attributedFounder?.username ?? null,
        }),
      );
    }
    return result;
  } catch {
    return new Map();
  }
}

async function listConclusionArticles(
  organizationId: string,
  limit: number,
): Promise<HomeArticleCard[]> {
  const rows = await listPublishedArticles(limit);
  if (rows.length === 0) return [];

  const authorByCid = await authorByConclusionId(
    organizationId,
    rows.map((r) => r.sourceConclusionId),
  );

  return rows.map((row) => {
    const subtitleSource =
      row.payload.article?.bodyMarkdown ||
      row.payload.evidenceSummary ||
      row.payload.rationale ||
      "";
    const readingSource = row.payload.article?.bodyMarkdown || "";
    return {
      id: row.id,
      href: `/c/${encodeURIComponent(row.slug)}`,
      title: row.payload.conclusionText,
      subtitle: deriveSubtitle(subtitleSource),
      publishedAt: row.publishedAt,
      authorDisplayName: authorByCid.get(row.sourceConclusionId) || "The firm",
      readingTimeMin: readingTimeMinutes(readingSource),
      source: "conclusion",
    };
  });
}

/**
 * Latest published long-form articles for the Articles rail.
 *
 * Bridges the two publish paths:
 *   - PublishedConclusion (kind = 'ARTICLE') → /c/[slug]
 *   - Upload (publishedAt, visibility = 'org')  → /post/[slug]
 *
 * Whichever path flipped the "is public" bit, the homepage surfaces
 * it within one render cycle.
 */
export async function listHomepageArticles(
  limit = 5,
): Promise<HomeArticleCard[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  const [uploads, conclusions] = await Promise.all([
    listUploadArticles(organizationId, limit),
    listConclusionArticles(organizationId, limit),
  ]);

  const merged = [...uploads, ...conclusions];
  merged.sort(compareCardsByPublishedAtDesc);
  return merged.slice(0, limit);
}

// ── Conclusions rail ──────────────────────────────────────────────────

/**
 * Latest published reviewed conclusions (kind = 'CONCLUSION') for the
 * Conclusions rail. Skips articles — those go on the Articles rail.
 * Returns the latest revision per slug.
 */
export async function listHomepageConclusions(
  limit = 8,
): Promise<HomeConclusionCard[]> {
  const organizationId = await resolvePublicOrganizationId();
  if (!organizationId) return [];

  try {
    const db = await loadDb();
    // Use a raw query because the Prisma schema doesn't have a
    // composite filter for "kind != ARTICLE and latest version per
    // slug" that's both correct and cheap. The DISTINCT-ON pattern
    // gives us exactly one row per slug, the newest version.
    const rows = await db.$queryRaw<
      {
        id: string;
        slug: string;
        version: number;
        publishedAt: Date | string;
        payloadJson: string;
      }[]
    >`
      SELECT DISTINCT ON (slug)
        id,
        slug,
        version,
        "publishedAt",
        "payloadJson"
      FROM "PublishedConclusion"
      WHERE "organizationId" = ${organizationId}
        AND kind = 'CONCLUSION'
      ORDER BY slug, version DESC
    `;

    const cards: HomeConclusionCard[] = rows.map((row) => {
      let parsed: { conclusionText?: string; evidenceSummary?: string; rationale?: string } = {};
      try {
        const value = JSON.parse(row.payloadJson);
        if (value && typeof value === "object" && !Array.isArray(value)) {
          parsed = value as typeof parsed;
        }
      } catch {
        parsed = {};
      }
      const title =
        (typeof parsed.conclusionText === "string" && parsed.conclusionText) ||
        row.slug;
      const subtitleSource =
        (typeof parsed.evidenceSummary === "string" && parsed.evidenceSummary) ||
        (typeof parsed.rationale === "string" && parsed.rationale) ||
        "";
      return {
        id: row.id,
        href: `/c/${encodeURIComponent(row.slug)}`,
        title,
        subtitle: deriveSubtitle(subtitleSource),
        publishedAt: toIsoString(row.publishedAt),
        version: row.version,
      };
    });

    cards.sort(compareCardsByPublishedAtDesc);
    return cards.slice(0, limit);
  } catch (error) {
    if (shouldLogOptionalDbError(error)) {
      console.error("[publicSurface] conclusion query failed:", error);
    }
    return [];
  }
}

// ── Conversion: legacy PublishedConclusion → HomeConclusionCard ───────
// Used by tests; lets a snapshot drive the rail without going through
// the database.

export function conclusionCardFromPublished(
  row: PublishedConclusion,
): HomeConclusionCard {
  const subtitleSource =
    row.payload.evidenceSummary || row.payload.rationale || "";
  return {
    id: row.id,
    href: `/c/${encodeURIComponent(row.slug)}`,
    title: row.payload.conclusionText,
    subtitle: deriveSubtitle(subtitleSource),
    publishedAt: row.publishedAt,
    version: row.version,
  };
}
