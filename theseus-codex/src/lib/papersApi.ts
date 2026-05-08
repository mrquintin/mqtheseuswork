import { promises as fs } from "node:fs";
import path from "node:path";

/**
 * papersApi — server-side surface for the auto-paper review queue.
 *
 * The .tex file under docs/research/auto/<slug>/paper.tex is the
 * authoritative artifact; the PDF is a build product. This module
 * is a thin file-system reader/writer over that directory tree, so
 * the founder workspace can list drafts, read their .tex, edit it,
 * flip review state, and (separately) request a PDF rebuild.
 *
 * It deliberately does NOT auto-publish. Promotion to the public
 * /research/[slug] surface is a separate, founder-confirmed step
 * that flips review_state to "published" and copies the build
 * artifacts into the public-facing directory.
 */

export const DEFAULT_PAPER_ROOT = "docs/research/auto";
export const PUBLIC_PAPER_ROOT = "docs/research/published";
export const DISCLOSURE_LABEL = "machine-drafted, founder-reviewed";

export type PaperReviewState =
  | "pending"
  | "edit-and-keep"
  | "edit-and-publish"
  | "rejected"
  | "published";

const ALLOWED_REVIEW_STATES: ReadonlySet<PaperReviewState> = new Set([
  "pending",
  "edit-and-keep",
  "edit-and-publish",
  "rejected",
  "published",
]);

export type PaperSidecar = {
  slug: string;
  cluster_id: string;
  lead_conclusion_id: string;
  conclusion_ids: string[];
  methodology_profile_id: string;
  resolved_forecast_prediction_ids: string[];
  disclosure: string;
  review_state: PaperReviewState;
  reviewer?: string;
  generated_at: string;
  review_updated_at?: string;
  tex_path: string;
  pdf_path: string | null;
};

function _repoRoot(): string {
  return process.env.THESEUS_REPO_ROOT
    ? process.env.THESEUS_REPO_ROOT
    : path.resolve(process.cwd(), "..");
}

function _papersRoot(): string {
  const override = process.env.THESEUS_PAPERS_ROOT;
  if (override) return override;
  return path.join(_repoRoot(), DEFAULT_PAPER_ROOT);
}

function _publishedRoot(): string {
  const override = process.env.THESEUS_PUBLISHED_PAPERS_ROOT;
  if (override) return override;
  return path.join(_repoRoot(), PUBLIC_PAPER_ROOT);
}

function _validateSlug(slug: string): string {
  if (!/^[a-z0-9][a-z0-9-]{0,127}$/.test(slug)) {
    throw new Error(`invalid paper slug: ${slug}`);
  }
  return slug;
}

async function _readSidecar(slug: string): Promise<PaperSidecar | null> {
  const dir = path.join(_papersRoot(), _validateSlug(slug));
  const sidecarPath = path.join(dir, "paper.json");
  try {
    const raw = await fs.readFile(sidecarPath, "utf-8");
    const parsed = JSON.parse(raw) as Partial<PaperSidecar>;
    const tex = path.join(dir, "paper.tex");
    const pdf = path.join(dir, "paper.pdf");
    let pdfExists = false;
    try {
      await fs.access(pdf);
      pdfExists = true;
    } catch {
      pdfExists = false;
    }
    return {
      slug,
      cluster_id: String(parsed.cluster_id ?? ""),
      lead_conclusion_id: String(parsed.lead_conclusion_id ?? ""),
      conclusion_ids: Array.isArray(parsed.conclusion_ids)
        ? parsed.conclusion_ids.map(String)
        : [],
      methodology_profile_id: String(parsed.methodology_profile_id ?? ""),
      resolved_forecast_prediction_ids: Array.isArray(
        parsed.resolved_forecast_prediction_ids,
      )
        ? parsed.resolved_forecast_prediction_ids.map(String)
        : [],
      disclosure: String(parsed.disclosure ?? DISCLOSURE_LABEL),
      review_state: (ALLOWED_REVIEW_STATES.has(
        (parsed.review_state ?? "pending") as PaperReviewState,
      )
        ? parsed.review_state
        : "pending") as PaperReviewState,
      reviewer: parsed.reviewer ? String(parsed.reviewer) : undefined,
      generated_at: String(parsed.generated_at ?? ""),
      review_updated_at: parsed.review_updated_at
        ? String(parsed.review_updated_at)
        : undefined,
      tex_path: tex,
      pdf_path: pdfExists ? pdf : null,
    };
  } catch {
    return null;
  }
}

export async function listPaperDrafts(): Promise<PaperSidecar[]> {
  const root = _papersRoot();
  let entries: string[] = [];
  try {
    entries = await fs.readdir(root);
  } catch {
    return [];
  }
  const drafts: PaperSidecar[] = [];
  for (const entry of entries.sort()) {
    const sidecar = await _readSidecar(entry);
    if (sidecar) drafts.push(sidecar);
  }
  return drafts;
}

export async function getPaperDraft(slug: string): Promise<PaperSidecar | null> {
  return _readSidecar(slug);
}

export async function readPaperTex(slug: string): Promise<string> {
  const dir = path.join(_papersRoot(), _validateSlug(slug));
  return fs.readFile(path.join(dir, "paper.tex"), "utf-8");
}

export async function writePaperTex(
  slug: string,
  body: string,
  options?: { reviewer?: string },
): Promise<void> {
  const dir = path.join(_papersRoot(), _validateSlug(slug));
  const texPath = path.join(dir, "paper.tex");
  await fs.access(texPath);
  if (!body.includes(DISCLOSURE_LABEL)) {
    throw new Error(
      `refusing to write paper.tex without "${DISCLOSURE_LABEL}" disclosure label`,
    );
  }
  await fs.writeFile(texPath, body, "utf-8");
  await _patchSidecar(slug, (s) => ({
    ...s,
    review_updated_at: new Date().toISOString(),
    reviewer: options?.reviewer ?? s.reviewer,
  }));
}

export async function setPaperReviewState(
  slug: string,
  next: PaperReviewState,
  options?: { reviewer?: string },
): Promise<PaperSidecar> {
  if (!ALLOWED_REVIEW_STATES.has(next)) {
    throw new Error(`invalid review state: ${next}`);
  }
  const updated = await _patchSidecar(slug, (s) => ({
    ...s,
    review_state: next,
    reviewer: options?.reviewer ?? s.reviewer,
    review_updated_at: new Date().toISOString(),
  }));
  return updated;
}

async function _patchSidecar(
  slug: string,
  patch: (s: PaperSidecar) => PaperSidecar,
): Promise<PaperSidecar> {
  const sidecar = await _readSidecar(slug);
  if (!sidecar) throw new Error(`paper draft not found: ${slug}`);
  const next = patch(sidecar);
  const dir = path.join(_papersRoot(), _validateSlug(slug));
  const sidecarPath = path.join(dir, "paper.json");
  const onDisk = {
    cluster_id: next.cluster_id,
    lead_conclusion_id: next.lead_conclusion_id,
    conclusion_ids: next.conclusion_ids,
    methodology_profile_id: next.methodology_profile_id,
    resolved_forecast_prediction_ids: next.resolved_forecast_prediction_ids,
    disclosure: DISCLOSURE_LABEL,
    review_state: next.review_state,
    reviewer: next.reviewer,
    generated_at: next.generated_at,
    review_updated_at: next.review_updated_at,
  };
  await fs.writeFile(sidecarPath, JSON.stringify(onDisk, null, 2), "utf-8");
  return next;
}

export async function listPublishedPapers(): Promise<PaperSidecar[]> {
  const root = _publishedRoot();
  let entries: string[] = [];
  try {
    entries = await fs.readdir(root);
  } catch {
    return [];
  }
  const out: PaperSidecar[] = [];
  for (const entry of entries.sort()) {
    const dir = path.join(root, entry);
    const sidecarPath = path.join(dir, "paper.json");
    try {
      const raw = await fs.readFile(sidecarPath, "utf-8");
      const parsed = JSON.parse(raw) as Partial<PaperSidecar>;
      const pdf = path.join(dir, "paper.pdf");
      let pdfExists = false;
      try {
        await fs.access(pdf);
        pdfExists = true;
      } catch {
        pdfExists = false;
      }
      out.push({
        slug: entry,
        cluster_id: String(parsed.cluster_id ?? ""),
        lead_conclusion_id: String(parsed.lead_conclusion_id ?? ""),
        conclusion_ids: Array.isArray(parsed.conclusion_ids)
          ? parsed.conclusion_ids.map(String)
          : [],
        methodology_profile_id: String(parsed.methodology_profile_id ?? ""),
        resolved_forecast_prediction_ids: Array.isArray(
          parsed.resolved_forecast_prediction_ids,
        )
          ? parsed.resolved_forecast_prediction_ids.map(String)
          : [],
        disclosure: String(parsed.disclosure ?? DISCLOSURE_LABEL),
        review_state: "published",
        reviewer: parsed.reviewer ? String(parsed.reviewer) : undefined,
        generated_at: String(parsed.generated_at ?? ""),
        review_updated_at: parsed.review_updated_at
          ? String(parsed.review_updated_at)
          : undefined,
        tex_path: path.join(dir, "paper.tex"),
        pdf_path: pdfExists ? pdf : null,
      });
    } catch {
      continue;
    }
  }
  return out;
}

export async function getPublishedPaper(
  slug: string,
): Promise<PaperSidecar | null> {
  const root = _publishedRoot();
  const dir = path.join(root, _validateSlug(slug));
  try {
    const raw = await fs.readFile(path.join(dir, "paper.json"), "utf-8");
    const parsed = JSON.parse(raw) as Partial<PaperSidecar>;
    const pdf = path.join(dir, "paper.pdf");
    let pdfExists = false;
    try {
      await fs.access(pdf);
      pdfExists = true;
    } catch {
      pdfExists = false;
    }
    return {
      slug,
      cluster_id: String(parsed.cluster_id ?? ""),
      lead_conclusion_id: String(parsed.lead_conclusion_id ?? ""),
      conclusion_ids: Array.isArray(parsed.conclusion_ids)
        ? parsed.conclusion_ids.map(String)
        : [],
      methodology_profile_id: String(parsed.methodology_profile_id ?? ""),
      resolved_forecast_prediction_ids: Array.isArray(
        parsed.resolved_forecast_prediction_ids,
      )
        ? parsed.resolved_forecast_prediction_ids.map(String)
        : [],
      disclosure: String(parsed.disclosure ?? DISCLOSURE_LABEL),
      review_state: "published",
      reviewer: parsed.reviewer ? String(parsed.reviewer) : undefined,
      generated_at: String(parsed.generated_at ?? ""),
      review_updated_at: parsed.review_updated_at
        ? String(parsed.review_updated_at)
        : undefined,
      tex_path: path.join(dir, "paper.tex"),
      pdf_path: pdfExists ? pdf : null,
    };
  } catch {
    return null;
  }
}

export async function readPublishedPaperPdf(
  slug: string,
): Promise<Buffer | null> {
  const root = _publishedRoot();
  const dir = path.join(root, _validateSlug(slug));
  try {
    return await fs.readFile(path.join(dir, "paper.pdf"));
  } catch {
    return null;
  }
}

export function plainProseSummary(sidecar: PaperSidecar): string {
  const n = sidecar.conclusion_ids.length;
  const f = sidecar.resolved_forecast_prediction_ids.length;
  return (
    `This paper distills ${n} firm conclusion(s) anchored on ` +
    `${sidecar.lead_conclusion_id} under methodology profile ` +
    `${sidecar.methodology_profile_id}, stress-tested against ${f} ` +
    `resolved forecast(s). It is ${DISCLOSURE_LABEL}.`
  );
}
