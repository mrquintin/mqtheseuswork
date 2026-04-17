/**
 * Central registry of on-page explanation copy for every Codex page.
 *
 * Using a single registry instead of an inline `<PageHelp>` call on each
 * page has two advantages:
 *   1. One source of truth for copy — when wording changes, change one file.
 *   2. Zero-footprint deploy — adding a help banner to 25 pages is a matter
 *      of adding 25 entries here, not editing 25 `page.tsx` files.
 *
 * Keys are pathnames. Dynamic segments use literal strings (e.g.
 * `/conclusions/[id]`); the resolver in `<AutoPageHelp />` normalizes
 * concrete URLs (`/conclusions/abc123`) to the template form.
 *
 * Copy convention (mirror `PageHelp.tsx`):
 *   - `title`   — page name in plain language
 *   - `purpose` — one sentence: what data does this page show?
 *   - `howTo`   — one sentence: when/why would I come here, or main action
 */

export type PageHelpEntry = {
  title: string;
  purpose: string;
  howTo?: string;
};

export const PAGE_HELP_REGISTRY: Readonly<Record<string, PageHelpEntry>> = {
  // ── Workspace ───────────────────────────────────────────────────────────
  "/dashboard": {
    title: "Dashboard",
    purpose:
      "Your firm's latest activity at a glance — recent uploads, newly synthesized conclusions, and drift events the coherence engine flagged.",
    howTo:
      "Use this as your daily landing page. Click any conclusion for its full lineage; use Upload (top right) to add new material.",
  },
  "/upload": {
    title: "Upload",
    purpose:
      "Drop files to feed the epistemic engine. Text formats (.md, .txt, .vtt, .jsonl) are ingested inline; PDFs and audio require a binary-storage backend.",
    howTo:
      "Drag and drop or use the file picker. Status auto-refreshes as Noosphere ingests the file, extracts claims, and synthesizes conclusions.",
  },
  "/conclusions": {
    title: "Conclusions",
    purpose:
      "Firm-level claims the engine has synthesized from your uploads, grouped by confidence tier (firm, founder, open).",
    howTo:
      "Click any conclusion for its full lineage — provenance, cascade, peer reviews. Use the tier buttons to filter, or Replay (top of the list) to see what the firm would have concluded at an earlier date.",
  },

  // ── Review (coherence & tensions) ───────────────────────────────────────
  "/contradictions": {
    title: "Contradictions",
    purpose:
      "Claim pairs the coherence engine flagged as incompatible, ranked by severity.",
    howTo:
      "Each row shows two statements and a six-layer breakdown of where they disagree. Severity > 0.7 is worth a founder look.",
  },
  "/open-questions": {
    title: "Open questions",
    purpose:
      "Tensions between claims that the system couldn't resolve automatically — candidates for deliberate discussion.",
    howTo:
      "Each open question links the two competing claims and summarizes why the layers disagreed. Discuss in the next session.",
  },
  "/adversarial": {
    title: "Adversarial",
    purpose:
      "Structured objections the system generated against your firm-tier conclusions, with coherence scores.",
    howTo:
      "Use the override action on each row to mark a challenge as `addressed` (answered elsewhere) or `fatal` (force-demotes the conclusion). `fallen` challenges require human review.",
  },
  "/q/review": {
    title: "Layer review",
    purpose:
      "Coherence disputes where the six layers disagreed with each other — the aggregator's verdict may be wrong.",
    howTo:
      "Cast your human verdict here when layer consensus is weak. Your override is used as training signal for future calibration.",
  },
  "/scoreboard": {
    title: "Calibration",
    purpose:
      "Your firm's track record on predictions, broken down by author and domain (Brier / log-loss / decile bins).",
    howTo:
      "Click an author for drill-down. Predictions in [0.45, 0.55] are excluded as honest uncertainty. Weak domains are surfaced to the research advisor.",
  },

  // ── Library (external knowledge) ────────────────────────────────────────
  "/voices": {
    title: "Voices",
    purpose:
      "External thinkers (non-founders) whose claims the system tracks alongside your own.",
    howTo:
      "Use this to see where the firm's position aligns with or diverges from canonical voices in the field. Click a voice for their full claim list.",
  },
  "/voices/[id]": {
    title: "Voice",
    purpose:
      "One external thinker's claims, grouped by topic, with relative-to-firm stance indicators.",
    howTo:
      "The stance badges show whether your firm agrees, disagrees, or is silent on each of this voice's positions.",
  },
  "/literature": {
    title: "Literature",
    purpose:
      "External reading material (PDFs, arXiv abstracts, etc.) ingested into the evidence pool.",
    howTo:
      "Use `noosphere literature` CLI commands to add more. Items become available for grounding reading suggestions in the Research tab.",
  },
  "/reading-queue": {
    title: "Reading queue",
    purpose:
      "Readings the research advisor suggested, ordered by urgency and grounded in specific claim matches from the Literature pool.",
    howTo:
      "Mark items done / skipped as you work through them; your progress feeds back into the advisor.",
  },
  "/research": {
    title: "Research",
    purpose:
      "Research-advisor suggestions: topics and readings prioritized for the next founder discussion.",
    howTo:
      "Each suggestion references a specific session or claim chain. Click through to see the grounding evidence.",
  },

  // ── Publication ─────────────────────────────────────────────────────────
  "/publication": {
    title: "Publication",
    purpose:
      "Internal moderation queue before conclusions become part of the firm's public publications.",
    howTo:
      "Use `Queue` to enqueue a firm-tier conclusion for review, `Review` to approve / reject / ask for revisions, and `Export` to push the approved bundle to the static public site.",
  },

  // ── Ops (Round-3 operator pages) ────────────────────────────────────────
  "/provenance": {
    title: "Provenance",
    purpose:
      "Extraction chain for every claim — how raw text became a structured claim with author, topic, and embedding.",
    howTo:
      "Export as CSV / JSON for audit. Use Search to find a specific claim id or extraction method.",
  },
  "/eval": {
    title: "Eval runs",
    purpose:
      "Benchmark suite runs over the coherence + synthesis pipeline against gold-standard fixtures.",
    howTo:
      "Compare runs across time to catch regressions after model upgrades. Click a run to see per-case results.",
  },
  "/eval/runs/[runId]": {
    title: "Eval run detail",
    purpose:
      "Per-case results for one evaluation run, with expected vs. observed diffs.",
    howTo:
      "Use the diff view to see exactly where the pipeline's verdict differs from the fixture's expected verdict.",
  },
  "/post-mortem": {
    title: "Post-mortem",
    purpose:
      "Conclusions that were later retracted — what the engine believed and why it turned out wrong.",
    howTo:
      "This is the firm's failure-mode journal. Read before betting on a tier-2 conclusion in a high-stakes context.",
  },
  "/decay": {
    title: "Decay",
    purpose:
      "Firm conclusions whose supporting evidence has gone stale (embeddings drifted, claims superseded, model-version mismatch).",
    howTo:
      "Use the Revalidate button to force a fresh coherence check under the current encoder.",
  },
  "/rigor-gate": {
    title: "Rigor gate",
    purpose:
      "Publication submissions requiring a rigor-gate check — decorator verification, meta-analysis, adversarial engagement, clarity.",
    howTo:
      "Submit new items via the form, or click any pending item to see the reviewer checklist and override if needed.",
  },
  "/rigor-gate/[submissionId]": {
    title: "Rigor gate submission",
    purpose:
      "One submission's checklist and override state.",
    howTo:
      "Use Override only with justification. The override is logged to the audit trail.",
  },
  "/methods": {
    title: "Methods",
    purpose:
      "Registered coherence / synthesis methods this firm's pipeline uses, plus unreleased candidate versions.",
    howTo:
      "Each method version is signed and provenance-tracked. Use `Candidates` to review proposed new methods before they ship.",
  },
  "/methods/candidates": {
    title: "Method candidates",
    purpose:
      "Proposed new methods that have not yet been released into the active pipeline.",
    howTo:
      "Promote a candidate once it passes the rigor gate; each promotion bumps its version and signs the new release.",
  },
  "/methods/[name]/[version]": {
    title: "Method version",
    purpose:
      "Single method version: signature, parameters, provenance, documentation.",
    howTo:
      "Use `Package` to generate a MIP bundle for this version, or `Document` to regenerate its method card.",
  },
  "/founders": {
    title: "Founders",
    purpose:
      "Co-founders of the firm and their upload / claim contributions, with quick stats.",
    howTo:
      "Click any founder to see their claim history. Use Replay to filter by a historical date.",
  },
  "/cascade/[conclusionId]": {
    title: "Cascade",
    purpose:
      "Inference tree for one conclusion — what downstream claims depend on it, recursively.",
    howTo:
      "Expand nodes to trace how changing the root conclusion would ripple through the firm's belief graph.",
  },
  "/peer-review/[conclusionId]": {
    title: "Peer review",
    purpose:
      "Founder reviews of a single conclusion (endorse / challenge / abstain), plus a button to run a new review.",
    howTo:
      "Run a review to put your vote on record; challenges contribute to the conclusion's confidence score.",
  },
  "/sessions/[id]/reflection": {
    title: "Session reflection",
    purpose:
      "Post-session bundle for a Dialectic recording: interventions the live interlocutor surfaced, with founder ratings.",
    howTo:
      "Rate each intervention as high-value / low-value / annoying so the interlocutor tunes future sessions.",
  },
};

/** Normalize a concrete pathname (`/voices/abc123`) to a registry key
 * (`/voices/[id]`). Returns the concrete pathname if no dynamic match. */
export function normalizePath(pathname: string): string {
  if (PAGE_HELP_REGISTRY[pathname]) return pathname;

  // Try each registry key that contains a bracket; replace the bracketed
  // segment with the concrete URL's segment and see if it matches.
  for (const key of Object.keys(PAGE_HELP_REGISTRY)) {
    if (!key.includes("[")) continue;
    const keySegments = key.split("/");
    const pathSegments = pathname.split("/");
    if (keySegments.length !== pathSegments.length) continue;
    const isMatch = keySegments.every(
      (seg, i) => seg === pathSegments[i] || seg.startsWith("["),
    );
    if (isMatch) return key;
  }
  return pathname;
}
