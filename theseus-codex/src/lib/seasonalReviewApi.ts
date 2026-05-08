import { promises as fs } from "node:fs";
import path from "node:path";

/**
 * seasonalReviewApi — server-side surface for quarterly seasonal reviews.
 *
 * The .tex file under docs/seasonal/<slug>/review.tex is the
 * narrative-bearing artifact and the .json sibling is the
 * structured-object the web view renders. The PDF is a build product;
 * the .tex is the source of truth.
 *
 * Reads only — sign-off (review_state flips) is performed by the
 * Python CLI / a separate founder-triage route. The web view never
 * promotes a draft on its own.
 */

export const DEFAULT_SEASONAL_ROOT = "docs/seasonal";
export const DISCLOSURE_LABEL = "machine-drafted, founder-reviewed";

export type SeasonalReviewState =
  | "pending"
  | "approved"
  | "rejected"
  | "published";

const ALLOWED_STATES: ReadonlySet<SeasonalReviewState> = new Set([
  "pending",
  "approved",
  "rejected",
  "published",
]);

export type SeasonalSectionStatus = {
  data_available: boolean;
  note: string;
};

export type SeasonalMethodRow = {
  method_id: string;
  name: string;
  version: string;
  status: string;
};

export type SeasonalDriftRow = {
  target_id: string;
  drift_score: number;
  observed_at: string;
  notes: string;
};

export type SeasonalArticleRow = {
  slug: string;
  title: string;
  published_at: string;
};

export type SeasonalPrincipleRow = {
  text: string;
  domain_breadth: number;
  conviction_score: number;
};

export type SeasonalEditedConclusionRow = {
  conclusion_id: string;
  text_excerpt: string;
  edits_in_window: number;
};

export type SeasonalSelfCritiqueRow = {
  review_item_id: string;
  article_id: string;
  reason: string;
  created_at: string;
};

export type SeasonalStructuredReview = {
  window: {
    year: number;
    quarter: number;
    label: string;
    slug: string;
    start: string;
    end: string;
  };
  generated_at: string;
  methods: {
    status: SeasonalSectionStatus;
    active_count: number;
    deprecated_count: number;
    retired_count: number;
    active: SeasonalMethodRow[];
    deprecated: SeasonalMethodRow[];
    retired: SeasonalMethodRow[];
  };
  drift: {
    status: SeasonalSectionStatus;
    event_count: number;
    events: SeasonalDriftRow[];
  };
  calibration: {
    status: SeasonalSectionStatus;
    resolved_count: number;
    mean_brier: number | null;
    mean_log_loss: number | null;
  };
  open_questions: {
    status: SeasonalSectionStatus;
    resolved_count: number;
    added_count: number;
  };
  articles: {
    status: SeasonalSectionStatus;
    article_count: number;
    articles: SeasonalArticleRow[];
  };
  principles: {
    status: SeasonalSectionStatus;
    drafted_count: number;
    drafted: SeasonalPrincipleRow[];
  };
  edited_conclusions: {
    status: SeasonalSectionStatus;
    row_count: number;
    rows: SeasonalEditedConclusionRow[];
  };
  self_critique: {
    status: SeasonalSectionStatus;
    finding_count: number;
    findings: SeasonalSelfCritiqueRow[];
  };
};

export type SeasonalReviewSidecar = {
  slug: string;
  window: {
    year: number;
    quarter: number;
    label: string;
    start: string;
    end: string;
  };
  generated_at: string;
  structured: SeasonalStructuredReview;
  narrative: Record<string, string>;
  disclosure: string;
  review_state: SeasonalReviewState;
  reviewer?: string;
  review_updated_at?: string;
  tex_path: string;
  json_path: string;
  pdf_path: string | null;
};

function _repoRoot(): string {
  return process.env.THESEUS_REPO_ROOT
    ? process.env.THESEUS_REPO_ROOT
    : path.resolve(process.cwd(), "..");
}

function _seasonalRoot(): string {
  const override = process.env.THESEUS_SEASONAL_ROOT;
  if (override) return override;
  return path.join(_repoRoot(), DEFAULT_SEASONAL_ROOT);
}

function _validateSlug(slug: string): string {
  // Slugs follow ``<year>_Q<n>_Review`` exactly. The matcher accepts
  // any directory name with the same shape so a manually-renamed
  // historical slug (e.g. "_v2") still loads.
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(slug)) {
    throw new Error(`invalid seasonal review slug: ${slug}`);
  }
  return slug;
}

async function _readSidecar(
  slug: string,
): Promise<SeasonalReviewSidecar | null> {
  const dir = path.join(_seasonalRoot(), _validateSlug(slug));
  const sidecarPath = path.join(dir, "review.json");
  try {
    const raw = await fs.readFile(sidecarPath, "utf-8");
    const parsed = JSON.parse(raw) as Partial<SeasonalReviewSidecar>;
    const tex = path.join(dir, "review.tex");
    const pdf = path.join(dir, "review.pdf");
    let pdfExists = false;
    try {
      await fs.access(pdf);
      pdfExists = true;
    } catch {
      pdfExists = false;
    }
    const reviewState = (
      ALLOWED_STATES.has(
        (parsed.review_state ?? "pending") as SeasonalReviewState,
      )
        ? parsed.review_state
        : "pending"
    ) as SeasonalReviewState;
    if (!parsed.structured || !parsed.window) return null;
    return {
      slug,
      window: parsed.window,
      generated_at: String(parsed.generated_at ?? ""),
      structured: parsed.structured as SeasonalStructuredReview,
      narrative: (parsed.narrative ?? {}) as Record<string, string>,
      disclosure: String(parsed.disclosure ?? DISCLOSURE_LABEL),
      review_state: reviewState,
      reviewer: parsed.reviewer ? String(parsed.reviewer) : undefined,
      review_updated_at: parsed.review_updated_at
        ? String(parsed.review_updated_at)
        : undefined,
      tex_path: tex,
      json_path: sidecarPath,
      pdf_path: pdfExists ? pdf : null,
    };
  } catch {
    return null;
  }
}

export async function listSeasonalReviews(): Promise<SeasonalReviewSidecar[]> {
  const root = _seasonalRoot();
  let entries: string[] = [];
  try {
    entries = await fs.readdir(root);
  } catch {
    return [];
  }
  const reviews: SeasonalReviewSidecar[] = [];
  for (const entry of entries.sort().reverse()) {
    const sidecar = await _readSidecar(entry);
    if (sidecar) reviews.push(sidecar);
  }
  return reviews;
}

export async function getSeasonalReview(
  slug: string,
): Promise<SeasonalReviewSidecar | null> {
  return _readSidecar(slug);
}

export async function readSeasonalReviewPdf(
  slug: string,
): Promise<Buffer | null> {
  const dir = path.join(_seasonalRoot(), _validateSlug(slug));
  try {
    return await fs.readFile(path.join(dir, "review.pdf"));
  } catch {
    return null;
  }
}

export function isPublic(sidecar: SeasonalReviewSidecar): boolean {
  return sidecar.review_state === "published";
}
