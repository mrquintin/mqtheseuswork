/**
 * Sentence-level provenance heatmap helpers.
 *
 * Mirrors `noosphere.cascade.sentence_provenance.SentenceProvenanceReport`.
 * The Python assembler computes the report at publish time; we ship it
 * with the article HTML and render the gutter from it. This module
 * also provides a thin client-only fallback so a published article
 * with no precomputed report still gets a usable (but flatter)
 * heatmap.
 *
 * Privacy: the public projection produced by the Python side already
 * strips identifying detail for private sources before the payload
 * leaves the firm — TS-side code never sees private source ids.
 */

import type { PublishedArticleCitation } from "@/lib/conclusionsRead";

export const SENTENCE_PROVENANCE_SCHEMA = "theseus.sentenceProvenance.v1";

export interface SourceContribution {
  label: string;
  source_kind: string;
  source_id: string;
  edge_weight: number;
  credibility: number;
  effective: number;
  public: boolean;
  citation_verdict: string | null;
}

export interface SentenceProvenance {
  index: number;
  text_hash: string;
  provenance: number;
  source_labels: string[];
  private_source_count: number;
}

export interface SentenceProvenanceReport {
  schema: typeof SENTENCE_PROVENANCE_SCHEMA;
  conclusion_id: string;
  overall_provenance: number;
  sources: Record<string, SourceContribution>;
  sentences: SentenceProvenance[];
}

const CITE_MARKER = /\[S(\d+)\]/g;
// Same one-step block-level strip as the Python side so the two
// agree on which sentences exist in an article body.
const BLOCK_STRIP = /(^\s*(?:#{1,6}\s+.*?$|>\s+.*?$|[-*+]\s+|\d+\.\s+))/gm;
const SENTENCE_BOUNDARY = /(?<=[.!?])\s+(?=[A-Z(["'])/g;

export interface SentenceWithLabels {
  text: string;
  labels: string[];
}

export function splitSentences(bodyMarkdown: string): SentenceWithLabels[] {
  if (!bodyMarkdown) return [];
  let cleaned = bodyMarkdown.replace(BLOCK_STRIP, "");
  cleaned = cleaned.replace(/\n{2,}/g, " ");
  cleaned = cleaned.replace(/\s+/g, " ").trim();
  if (!cleaned) return [];
  const parts = cleaned.split(SENTENCE_BOUNDARY);
  return parts
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
    .map((text) => ({ text, labels: labelsIn(text) }));
}

export function labelsIn(sentence: string): string[] {
  const out: string[] = [];
  CITE_MARKER.lastIndex = 0;
  for (const m of sentence.matchAll(CITE_MARKER)) out.push(`S${m[1]}`);
  return out;
}

/**
 * Validate that the report we received matches the article body. If
 * the sentence count differs (e.g. the article was edited after the
 * report was assembled), we drop back to the local fallback so the
 * gutter does not align mis-keyed cells against the visible text.
 */
export function reportMatchesBody(
  report: SentenceProvenanceReport | null | undefined,
  bodyMarkdown: string,
): report is SentenceProvenanceReport {
  if (!report || report.schema !== SENTENCE_PROVENANCE_SCHEMA) return false;
  const sentenceCount = splitSentences(bodyMarkdown).length;
  return report.sentences.length === sentenceCount;
}

/**
 * Build an emergency fallback report from the article body alone — no
 * cascade walk, no credibility ledger. Each cited sentence is given a
 * neutral 0.5 provenance; uncited sentences get a default of 0.4 so
 * the reader can still distinguish "anchored" from "uncited" rows.
 *
 * This is intentionally conservative: a fallback should look weaker
 * than a real report so the firm is honest that it could not show its
 * full evidence stack.
 */
export function fallbackReport(
  conclusionId: string,
  bodyMarkdown: string,
  citations: PublishedArticleCitation[],
): SentenceProvenanceReport {
  const sources: Record<string, SourceContribution> = {};
  for (const c of citations) {
    sources[c.label] = {
      label: c.label,
      source_kind: c.sourceKind,
      source_id: c.sourceId,
      edge_weight: 0.5,
      credibility: 0.5,
      effective: 0.25,
      public: Boolean(c.publicUrl),
      citation_verdict: null,
    };
  }
  const sentences = splitSentences(bodyMarkdown).map((s, index) => ({
    index,
    text_hash: shortHash(s.text),
    provenance: s.labels.length > 0 ? 0.5 : 0.4,
    source_labels: s.labels,
    private_source_count: 0,
  }));
  return {
    schema: SENTENCE_PROVENANCE_SCHEMA,
    conclusion_id: conclusionId,
    overall_provenance: 0.45,
    sources,
    sentences,
  };
}

/** Short, deterministic, dependency-free hash. Not crypto-grade — only
 *  used to key DOM cells back to sentences. 8 hex chars is plenty. */
export function shortHash(input: string): string {
  let h1 = 0xdeadbeef ^ 0;
  let h2 = 0x41c6ce57 ^ 0;
  for (let i = 0; i < input.length; i++) {
    const ch = input.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507);
  h1 ^= Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507);
  h2 ^= Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  const out = ((h2 >>> 0).toString(16) + (h1 >>> 0).toString(16)).slice(-8);
  return out.padStart(8, "0");
}

/**
 * Map a [0,1] provenance score to a discrete band. Three bands keeps
 * the visual language readable and accessibility-checkable: a screen
 * reader announces "weak / moderate / strong evidence" rather than a
 * raw decimal.
 */
export type ProvenanceBand = "weak" | "moderate" | "strong";

export function bandFor(provenance: number): ProvenanceBand {
  if (!Number.isFinite(provenance) || provenance < 0.35) return "weak";
  if (provenance < 0.6) return "moderate";
  return "strong";
}

export function describeBand(band: ProvenanceBand): string {
  if (band === "strong") return "Strong evidence support";
  if (band === "moderate") return "Moderate evidence support";
  return "Weak evidence support — inspect citations";
}

/**
 * Faint gutter tint colour for each band. Kept on a separate axis from
 * the article body so typography stays clean. The values are intentionally
 * low-alpha — the gutter should be readable, not loud.
 */
export function tintFor(band: ProvenanceBand): string {
  if (band === "strong") return "rgba(95, 168, 110, 0.28)";
  if (band === "moderate") return "rgba(214, 156, 63, 0.22)";
  return "rgba(201, 74, 31, 0.32)";
}

/**
 * Estimate the gzipped size of a serialised report. The Python perf
 * test enforces the 25KB budget; this helper exposes the live size to
 * the front end so an instrumentation hook can flag regressions.
 */
export function estimatedSerializedBytes(report: SentenceProvenanceReport): number {
  return JSON.stringify(report).length;
}

/**
 * Build a per-sentence summary string for the screen-reader-only
 * "provenance summary" affordance. Includes the band, the numeric
 * value, and the count of supporting sources (public + private).
 */
export function summaryForScreenReader(sentence: SentenceProvenance): string {
  const band = bandFor(sentence.provenance);
  const named = sentence.source_labels.length;
  const hidden = sentence.private_source_count;
  const total = named + hidden;
  const value = `${Math.round(sentence.provenance * 100)} of 100`;
  if (total === 0) return `${describeBand(band)}; provenance ${value}; no direct citations.`;
  const namedNote = named ? `${named} cited source${named === 1 ? "" : "s"}` : "";
  const hiddenNote = hidden ? `${hidden} private source${hidden === 1 ? "" : "s"}` : "";
  const tail = [namedNote, hiddenNote].filter(Boolean).join(", ");
  return `${describeBand(band)}; provenance ${value}; ${tail}.`;
}

/**
 * Toggle persistence: cookie/localStorage with a graceful default-off
 * when storage is restricted (Safari ITP, private mode).
 */
const TOGGLE_KEY = "theseus.provenance.gutterVisible";

export function readToggle(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(TOGGLE_KEY);
    return raw === "true";
  } catch {
    return false;
  }
}

export function writeToggle(value: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOGGLE_KEY, value ? "true" : "false");
  } catch {
    /* storage restricted; toggle becomes session-only */
  }
}

const TOOLTIP_KEY = "theseus.provenance.tipShown";

export function shouldShowFirstUseTip(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(TOOLTIP_KEY) !== "1";
  } catch {
    return false;
  }
}

export function markFirstUseTipShown(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOOLTIP_KEY, "1");
  } catch {
    /* swallow */
  }
}
