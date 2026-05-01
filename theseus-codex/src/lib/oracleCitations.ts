export const ORACLE_CITATION_TOKEN = /\[(C|U):([A-Za-z0-9_-]+)\]/g;
export const ORACLE_CITATION_TOKEN_EXACT = /^\[(C|U):([A-Za-z0-9_-]+)\]$/;

const PREVIEW_CHARS = 240;
const SURROUNDING_CONTEXT_CHARS = 200;

export type ResolvedCitation =
  | {
      type: "conclusion";
      id: string;
      tier: string;
      url: string | null;
      preview: string;
    }
  | {
      type: "upload";
      id: string;
      title: string;
      url: string | null;
      anchor: string | null;
      preview: string;
    };

export type ResolvedCitationMap = Record<string, ResolvedCitation>;

export interface OracleCitationSource {
  type: "conclusion" | "upload";
  id: string;
  label: string;
  tier?: string;
  topic?: string;
  text: string;
  url?: string | null;
  anchor?: string | null;
}

export interface OracleUploadChunk {
  uploadId: string;
  chunkId?: string | null;
  chunkIndex: number;
  text: string;
}

export interface OracleCitationStats {
  citationsResolved: number;
  citationsUnresolved: number;
}

interface CitationMatch {
  token: string;
  kind: "C" | "U";
  fragment: string;
  index: number;
}

function preview(text: string): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (cleaned.length <= PREVIEW_CHARS) return cleaned;
  return `${cleaned.slice(0, PREVIEW_CHARS - 1).trimEnd()}...`;
}

function normalizeLookup(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9_-]+/g, "");
}

function tokenizeForOverlap(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter((token) => token.length >= 3),
  );
}

function lexicalOverlapScore(sourceText: string, answerContext: string): number {
  const sourceTokens = tokenizeForOverlap(sourceText);
  const contextTokens = tokenizeForOverlap(answerContext);
  if (sourceTokens.size === 0 || contextTokens.size === 0) return 0;

  let overlap = 0;
  for (const token of contextTokens) {
    if (sourceTokens.has(token)) overlap++;
  }
  return overlap / Math.sqrt(sourceTokens.size);
}

function uniqueCitationMatches(answer: string): CitationMatch[] {
  const seen = new Set<string>();
  const matches: CitationMatch[] = [];
  ORACLE_CITATION_TOKEN.lastIndex = 0;

  for (const match of answer.matchAll(ORACLE_CITATION_TOKEN)) {
    const token = match[0];
    const kind = match[1] as "C" | "U";
    const fragment = match[2]!;
    if (match.index === undefined || seen.has(token)) continue;
    seen.add(token);
    matches.push({ token, kind, fragment, index: match.index });
  }

  return matches;
}

function findSource(
  sources: OracleCitationSource[],
  kind: "C" | "U",
  fragment: string,
): OracleCitationSource | null {
  const expectedType = kind === "C" ? "conclusion" : "upload";
  const candidates = sources.filter((source) => source.type === expectedType);
  const direct = candidates.find((source) => source.id.startsWith(fragment));
  if (direct) return direct;

  // Backward-compatible fallback for pre-resolution prompts that used short
  // upload titles in [U:...] rather than upload id prefixes.
  if (kind === "U") {
    const normalizedFragment = normalizeLookup(fragment);
    return (
      candidates.find((source) =>
        normalizeLookup(source.label).startsWith(normalizedFragment),
      ) ?? null
    );
  }

  return null;
}

function bestUploadChunk(
  uploadId: string,
  answer: string,
  match: CitationMatch,
  chunks: OracleUploadChunk[],
  fallbackText: string,
): { anchor: string | null; text: string } {
  const before = answer.slice(
    Math.max(0, match.index - SURROUNDING_CONTEXT_CHARS),
    match.index,
  );
  const after = answer.slice(
    match.index + match.token.length,
    match.index + match.token.length + SURROUNDING_CONTEXT_CHARS,
  );
  const context = `${before} ${after}`;
  const candidates = chunks.filter((chunk) => chunk.uploadId === uploadId);

  let best: OracleUploadChunk | null = null;
  let bestScore = -1;
  for (const chunk of candidates) {
    const score = lexicalOverlapScore(chunk.text.slice(0, PREVIEW_CHARS * 2), context);
    if (score > bestScore) {
      best = chunk;
      bestScore = score;
    }
  }

  if (best && bestScore > 0) {
    return {
      anchor: best.chunkId ? `chunk-${best.chunkId}` : null,
      text: best.text,
    };
  }

  return { anchor: null, text: fallbackText };
}

export function conclusionCitationPath(id: string): string {
  return `/conclusions/${encodeURIComponent(id)}`;
}

export function uploadCitationPath(id: string): string {
  return `/transcripts/${encodeURIComponent(id)}`;
}

export function citationHref(citation: ResolvedCitation): string | null {
  if (!citation.url) return null;
  if (citation.type !== "upload" || !citation.anchor) return citation.url;
  return `${citation.url}?anchor=${encodeURIComponent(citation.anchor)}`;
}

export function maskCitationToken(token: string): string {
  const parsed = ORACLE_CITATION_TOKEN_EXACT.exec(token);
  if (!parsed) return "[citation:***]";
  const kind = parsed[1];
  const id = parsed[2]!;
  if (id.length <= 4) return `[${kind}:***]`;
  return `[${kind}:${id.slice(0, 2)}***${id.slice(-2)}]`;
}

export function resolveOracleCitations(params: {
  answer: string;
  sources: OracleCitationSource[];
  uploadChunks?: OracleUploadChunk[];
}): { citations: ResolvedCitationMap } & OracleCitationStats {
  const uploadChunks = params.uploadChunks ?? [];
  const citations: ResolvedCitationMap = {};
  let citationsResolved = 0;
  let citationsUnresolved = 0;

  for (const match of uniqueCitationMatches(params.answer)) {
    const source = findSource(params.sources, match.kind, match.fragment);

    if (!source) {
      citationsUnresolved++;
      citations[match.token] =
        match.kind === "C"
          ? {
              type: "conclusion",
              id: match.fragment,
              tier: "unknown",
              url: null,
              preview: "",
            }
          : {
              type: "upload",
              id: match.fragment,
              title: match.fragment,
              url: null,
              anchor: null,
              preview: "",
            };
      continue;
    }

    citationsResolved++;
    if (source.type === "conclusion") {
      citations[match.token] = {
        type: "conclusion",
        id: source.id,
        tier: source.tier || source.label,
        url: conclusionCitationPath(source.id),
        preview: preview(source.text),
      };
      continue;
    }

    const best = bestUploadChunk(
      source.id,
      params.answer,
      match,
      uploadChunks,
      source.text,
    );
    citations[match.token] = {
      type: "upload",
      id: source.id,
      title: source.label,
      url: uploadCitationPath(source.id),
      anchor: best.anchor,
      preview: preview(best.text),
    };
  }

  return { citations, citationsResolved, citationsUnresolved };
}
