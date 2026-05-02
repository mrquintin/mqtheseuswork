export type ConversationChunkInput = {
  id: string;
  index?: number;
  text: string;
  startMs?: number | null;
  endMs?: number | null;
  speakerLabel?: string | null;
};

export type CatalystKind =
  | "question-response"
  | "agreement"
  | "disagreement"
  | "causal-continuation"
  | "conceptual-carry"
  | "neutral-handoff";

export type SpeakerGeometry = {
  id: string;
  label: string;
  turns: number;
  wordCount: number;
  questionTurns: number;
  shareOfWords: number;
  averageTurnLength: number;
  firstChunkId: string;
  lastChunkId: string;
  topRepeatedTerms: string[];
  words: number;
  share: number;
  averageTurnWords: number;
  terms: string[];
};

export type ExchangeEdge = {
  id: string;
  source: string;
  target: string;
  sourceLabel: string;
  targetLabel: string;
  count: number;
  weight: number;
  sharedTerms: string[];
  turns: number;
};

export type CatalystMoment = {
  id: string;
  fromChunkId: string;
  toChunkId: string;
  source: string;
  target: string;
  sourceLabel: string;
  targetLabel: string;
  kind: CatalystKind;
  score: number;
  sharedTerms: string[];
  fromExcerpt: string;
  toExcerpt: string;
  anchor: string;
};

export type ConversationGeometry = {
  speakers: SpeakerGeometry[];
  edges: ExchangeEdge[];
  catalysts: CatalystMoment[];
  totalTurns: number;
  totalWords: number;
  totalHandoffs: number;
  hasSpeakerLabels: boolean;
  hasRealSpeakerLabels: boolean;
};

export type TranscriptForSeason = {
  id: string;
  title: string;
  createdAt: Date;
  chunks: ConversationChunkInput[];
};

export type YearEndConversationStats = {
  year: number;
  status: "locked" | "ready";
  transcriptCount: number;
  totalTurns: number;
  totalHandoffs: number;
  participantCount: number;
  topSpeakerLabel: string | null;
  topSpeakerShare: number;
  topBridgeLabel: string | null;
};

const STOPWORDS = new Set([
  "about",
  "after",
  "again",
  "almost",
  "also",
  "because",
  "before",
  "being",
  "between",
  "could",
  "exactly",
  "from",
  "have",
  "into",
  "just",
  "like",
  "maybe",
  "more",
  "people",
  "really",
  "right",
  "should",
  "that",
  "their",
  "there",
  "these",
  "thing",
  "think",
  "this",
  "those",
  "with",
  "would",
  "yeah",
]);

function stableSpeakerId(label: string): string {
  return (
    label
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "unattributed"
  );
}

function displaySpeakerLabel(chunk: ConversationChunkInput): string {
  return chunk.speakerLabel?.trim() || "Unattributed";
}

function hasAnySpeakerLabel(chunk: ConversationChunkInput): boolean {
  return Boolean(chunk.speakerLabel?.trim());
}

function isGenericSpeakerLabel(label: string): boolean {
  const normalized = label.trim().toLowerCase().replace(/\s+/g, " ");
  return (
    normalized === "" ||
    normalized === "speaker" ||
    normalized === "unknown" ||
    normalized === "unknown speaker" ||
    normalized === "unattributed" ||
    /^speaker[-_ :#]*[a-z0-9]+$/.test(normalized) ||
    /^participant[-_ :#]*[a-z0-9]+$/.test(normalized)
  );
}

function words(text: string): string[] {
  return text.toLowerCase().match(/[a-z0-9']+/g) ?? [];
}

function terms(text: string): string[] {
  return words(text).filter((word) => word.length >= 4 && !STOPWORDS.has(word));
}

function topRepeatedTerms(counts: Map<string, number>, limit: number): string[] {
  return [...counts.entries()]
    .filter(([, count]) => count > 1)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([term]) => term);
}

function uniqueIntersection(left: string[], right: string[]): string[] {
  const rightTerms = new Set(right);
  return [...new Set(left)].filter((term) => rightTerms.has(term)).slice(0, 5);
}

function excerpt(text: string, max = 128): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max - 3).trimEnd()}...`;
}

export function transcriptChunkAnchor(chunkId: string): string {
  return `chunk-${chunkId}`;
}

function orderedChunks(chunks: ConversationChunkInput[]): ConversationChunkInput[] {
  return chunks
    .map((chunk, inputOrder) => ({ chunk, inputOrder }))
    .sort((a, b) => {
      const leftIndex = a.chunk.index ?? a.inputOrder;
      const rightIndex = b.chunk.index ?? b.inputOrder;
      return leftIndex - rightIndex || a.inputOrder - b.inputOrder;
    })
    .map(({ chunk }) => chunk);
}

function classifyCatalyst(
  fromText: string,
  toText: string,
  sharedTerms: string[],
): CatalystKind {
  const previous = fromText.trim().toLowerCase();
  const next = toText.trim().toLowerCase();
  if (
    previous.includes("?") ||
    /^(who|what|when|where|why|how|do|does|did|can|could|would|should|is|are|was|were|will)\b/.test(previous)
  ) {
    return "question-response";
  }
  if (/^(yes|yep|yeah|exactly|right|agreed|agree|i agree|that's right)\b/.test(next)) {
    return "agreement";
  }
  if (/^(no|nope|but|however|although|i disagree|not exactly|that's wrong)\b/.test(next)) {
    return "disagreement";
  }
  if (
    /^(so|therefore|thus|hence|because|consequently|as a result|that means|which means)\b/.test(next) ||
    /\b(if|because|caused|causes|means|therefore|thus|hence|consequently)\b/.test(next)
  ) {
    return "causal-continuation";
  }
  if (sharedTerms.length >= 2) return "conceptual-carry";
  return "neutral-handoff";
}

function catalystScore(kind: CatalystKind, sharedTerms: string[], toText: string): number {
  const kindWeight: Record<CatalystKind, number> = {
    "question-response": 5,
    disagreement: 5,
    "causal-continuation": 4,
    agreement: 3,
    "conceptual-carry": 3,
    "neutral-handoff": 1,
  };
  const lengthBonus = Math.min(3, Math.floor(words(toText).length / 22));
  return kindWeight[kind] + sharedTerms.length + lengthBonus;
}

function emptyYearStats(year: number, status: YearEndConversationStats["status"]): YearEndConversationStats {
  return {
    year,
    status,
    transcriptCount: 0,
    totalTurns: 0,
    totalHandoffs: 0,
    participantCount: 0,
    topSpeakerLabel: null,
    topSpeakerShare: 0,
    topBridgeLabel: null,
  };
}

export function buildConversationGeometry(chunks: ConversationChunkInput[]): ConversationGeometry {
  const ordered = orderedChunks(chunks);
  const hasSpeakerLabels = ordered.some(hasAnySpeakerLabel);
  const hasRealSpeakerLabels = ordered.some((chunk) => {
    const label = chunk.speakerLabel?.trim();
    return Boolean(label && !isGenericSpeakerLabel(label));
  });
  const speakers = new Map<
    string,
    {
      id: string;
      label: string;
      turns: number;
      wordCount: number;
      questionTurns: number;
      firstChunkId: string;
      lastChunkId: string;
      termCounts: Map<string, number>;
    }
  >();
  const edges = new Map<string, ExchangeEdge>();
  const catalysts: CatalystMoment[] = [];

  let totalWords = 0;

  ordered.forEach((chunk, index) => {
    const label = displaySpeakerLabel(chunk);
    const id = stableSpeakerId(label);
    const chunkWords = words(chunk.text).length;
    totalWords += chunkWords;

    let speaker = speakers.get(id);
    if (!speaker) {
      speaker = {
        id,
        label,
        turns: 0,
        wordCount: 0,
        questionTurns: 0,
        firstChunkId: chunk.id,
        lastChunkId: chunk.id,
        termCounts: new Map(),
      };
      speakers.set(id, speaker);
    }

    speaker.turns += 1;
    speaker.wordCount += chunkWords;
    speaker.lastChunkId = chunk.id;
    if (chunk.text.includes("?")) speaker.questionTurns += 1;
    for (const term of terms(chunk.text)) {
      speaker.termCounts.set(term, (speaker.termCounts.get(term) ?? 0) + 1);
    }

    const next = ordered[index + 1];
    if (!next) return;

    const nextLabel = displaySpeakerLabel(next);
    const nextId = stableSpeakerId(nextLabel);
    if (id === nextId) return;

    const sharedTerms = uniqueIntersection(terms(chunk.text), terms(next.text));
    const kind = classifyCatalyst(chunk.text, next.text, sharedTerms);
    const score = catalystScore(kind, sharedTerms, next.text);

    catalysts.push({
      id: `${chunk.id}->${next.id}`,
      fromChunkId: chunk.id,
      toChunkId: next.id,
      source: id,
      target: nextId,
      sourceLabel: label,
      targetLabel: nextLabel,
      kind,
      score,
      sharedTerms,
      fromExcerpt: excerpt(chunk.text),
      toExcerpt: excerpt(next.text),
      anchor: transcriptChunkAnchor(next.id),
    });

    const edgeId = `${id}->${nextId}`;
    const edge = edges.get(edgeId) ?? {
      id: edgeId,
      source: id,
      target: nextId,
      sourceLabel: label,
      targetLabel: nextLabel,
      count: 0,
      weight: 0,
      sharedTerms: [],
      turns: 0,
    };
    edge.count += 1;
    edge.turns = edge.count;
    edge.weight += score;
    edge.sharedTerms = [...new Set([...edge.sharedTerms, ...sharedTerms])].slice(0, 5);
    edges.set(edgeId, edge);
  });

  const speakerRows = [...speakers.values()]
    .map((speaker) => {
      const repeatedTerms = topRepeatedTerms(speaker.termCounts, 5);
      const shareOfWords = totalWords > 0 ? speaker.wordCount / totalWords : 0;
      const averageTurnLength =
        speaker.turns > 0 ? speaker.wordCount / speaker.turns : 0;
      return {
        id: speaker.id,
        label: speaker.label,
        turns: speaker.turns,
        wordCount: speaker.wordCount,
        questionTurns: speaker.questionTurns,
        shareOfWords,
        averageTurnLength,
        firstChunkId: speaker.firstChunkId,
        lastChunkId: speaker.lastChunkId,
        topRepeatedTerms: repeatedTerms,
        words: speaker.wordCount,
        share: shareOfWords,
        averageTurnWords: averageTurnLength,
        terms: repeatedTerms,
      };
    })
    .sort((a, b) => b.wordCount - a.wordCount || a.label.localeCompare(b.label));

  const edgeRows = [...edges.values()].sort(
    (a, b) => b.weight - a.weight || b.count - a.count || a.id.localeCompare(b.id),
  );

  return {
    speakers: speakerRows,
    edges: edgeRows,
    catalysts,
    totalTurns: ordered.length,
    totalWords,
    totalHandoffs: edgeRows.reduce((sum, edge) => sum + edge.count, 0),
    hasSpeakerLabels,
    hasRealSpeakerLabels,
  };
}

function isYearClosed(year: number, now: Date): boolean {
  return now.getUTCFullYear() > year;
}

export function buildYearEndConversationStats(
  year: number,
  transcripts: TranscriptForSeason[],
  now = new Date(),
): YearEndConversationStats {
  if (!isYearClosed(year, now)) return emptyYearStats(year, "locked");

  const relevant = transcripts.filter((item) => item.createdAt.getUTCFullYear() === year);
  const geometries = relevant.map((item) => buildConversationGeometry(item.chunks));
  const speakerWords = new Map<string, { label: string; words: number }>();
  const bridgeWeights = new Map<string, { label: string; weight: number }>();
  let totalWords = 0;
  let totalTurns = 0;
  let totalHandoffs = 0;

  for (const geometry of geometries) {
    totalWords += geometry.totalWords;
    totalTurns += geometry.totalTurns;
    totalHandoffs += geometry.totalHandoffs;
    for (const speaker of geometry.speakers) {
      const existing = speakerWords.get(speaker.id) ?? { label: speaker.label, words: 0 };
      existing.words += speaker.wordCount;
      speakerWords.set(speaker.id, existing);
    }
    for (const edge of geometry.edges) {
      const existing = bridgeWeights.get(edge.id) ?? {
        label: `${edge.sourceLabel} -> ${edge.targetLabel}`,
        weight: 0,
      };
      existing.weight += edge.weight;
      bridgeWeights.set(edge.id, existing);
    }
  }

  const topSpeaker = [...speakerWords.values()].sort(
    (a, b) => b.words - a.words || a.label.localeCompare(b.label),
  )[0];
  const topBridge = [...bridgeWeights.values()].sort(
    (a, b) => b.weight - a.weight || a.label.localeCompare(b.label),
  )[0];

  return {
    year,
    status: "ready",
    transcriptCount: relevant.length,
    totalTurns,
    totalHandoffs,
    participantCount: speakerWords.size,
    topSpeakerLabel: topSpeaker?.label ?? null,
    topSpeakerShare: topSpeaker && totalWords > 0 ? topSpeaker.words / totalWords : 0,
    topBridgeLabel: topBridge?.label ?? null,
  };
}
