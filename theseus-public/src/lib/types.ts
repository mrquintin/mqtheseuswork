export type PublicCitation = { format: "bibtex" | "apa" | "ris"; block: string };

export type PublicConclusionPayload = {
  schema?: string;
  conclusionText: string;
  rationale?: string;
  topicHint?: string;
  evidenceSummary: string;
  exitConditions: string[];
  strongestObjection: { objection: string; firmAnswer: string };
  openQuestionsAdjacent: string[];
  voiceComparisons: { voice: string; stance: string }[];
  timeline: { at: string; label: string; detail?: string }[];
  whatWouldChangeOurMind: string[];
  citations: PublicCitation[];
};

export type PublicConclusion = {
  id: string;
  slug: string;
  version: number;
  sourceConclusionId: string;
  publishedAt: string;
  doi: string;
  zenodoRecordId: string;
  discountedConfidence: number;
  statedConfidence: number;
  calibrationDiscountReason: string;
  payload: PublicConclusionPayload;
};

export type PublicOpenQuestion = {
  id: string;
  summary: string;
  unresolvedReason: string;
  layerDisagreementSummary: string;
  createdAt: string;
};

export type PublicResponse = {
  id: string;
  publishedConclusionId: string;
  kind: string;
  body: string;
  citationUrl: string;
  status: string;
  createdAt: string;
  pseudonymous: boolean;
};

export type PublishedBundle = {
  schema: "theseus.publishedExport.v1";
  generatedAt: string;
  conclusions: PublicConclusion[];
  openQuestions: PublicOpenQuestion[];
  responses: PublicResponse[];
};
