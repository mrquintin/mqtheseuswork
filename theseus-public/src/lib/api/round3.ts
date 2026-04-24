import type { PublicConclusion } from "@/lib/types";
import { bundle } from "@/lib/bundle";

import raw from "../../../content/round3.json";

// ---- Types ----

export type MethodDoc = {
  name: string;
  version: string;
  doi: string;
  description: string;
  bibtex: string;
  downloadUrl: string;
  publishedAt: string;
  corpusHash: string;
  signature: string;
  parameters: Record<string, unknown>;
  versionHistory: { version: string; publishedAt: string; changeNote: string }[];
};

export type MIP = {
  name: string;
  version: string;
  description: string;
  adoptionInstructions: string;
  versionMatrix: { version: string; publishedAt: string; status: string }[];
  publishedAt: string;
  corpusHash: string;
  signature: string;
};

export type RigorMonthEntry = {
  month: string;
  passCount: number;
  failCount: number;
  topFailureCategories: { category: string; count: number }[];
};

export type FounderOverride = {
  id: string;
  conclusionId: string;
  field: string;
  originalValue: string;
  overriddenValue: string;
  justification: string;
  issuedAt: string;
  issuedBy: string;
};

export type DecayStat = {
  conclusionId: string;
  slug: string;
  currentConfidence: number;
  originalConfidence: number;
  decayRate: number;
  lastDecayEvent: string;
  totalDecayEvents: number;
};

export type ProvenanceSummary = {
  conclusionId: string;
  ledgerEntries: { hash: string; timestamp: string; action: string }[];
  corpusHashAtPublication: string;
};

export type AdversarialHistoryEntry = {
  round: number;
  reviewerRole: string;
  outcome: "pass" | "fail" | "conditional";
  summary: string;
};

export type Round3Bundle = {
  schema: "theseus.round3Export.v1";
  generatedAt: string;
  methods: MethodDoc[];
  mips: MIP[];
  rigorDashboard: RigorMonthEntry[];
  founderOverrides: FounderOverride[];
  decayStats: DecayStat[];
  provenance: Record<string, ProvenanceSummary>;
  adversarialHistory: Record<string, AdversarialHistoryEntry[]>;
};

// ---- Data ----

const r3 = raw as unknown as Round3Bundle;

// ---- Read-only fetchers ----

export function allMethods(): MethodDoc[] {
  return r3.methods.slice().sort((a, b) => a.name.localeCompare(b.name));
}

export function pickMethod(name: string, version?: string): MethodDoc | null {
  const matches = r3.methods.filter((m) => m.name === name);
  if (!matches.length) return null;
  if (version) return matches.find((m) => m.version === version) ?? null;
  return matches.reduce((a, b) => (b.publishedAt > a.publishedAt ? b : a));
}

export function allMips(): MIP[] {
  return r3.mips.slice().sort((a, b) => a.name.localeCompare(b.name));
}

export function pickMip(name: string, version?: string): MIP | null {
  const matches = r3.mips.filter((m) => m.name === name);
  if (!matches.length) return null;
  if (version) return matches.find((m) => m.version === version) ?? null;
  return matches.reduce((a, b) => (b.publishedAt > a.publishedAt ? b : a));
}

export function rigorDashboard(): RigorMonthEntry[] {
  return r3.rigorDashboard.slice().sort((a, b) => b.month.localeCompare(a.month));
}

export function allOverrides(): FounderOverride[] {
  return r3.founderOverrides.slice().sort((a, b) => b.issuedAt.localeCompare(a.issuedAt));
}

export function allDecayStats(): DecayStat[] {
  return r3.decayStats.slice().sort((a, b) => a.slug.localeCompare(b.slug));
}

export function provenanceFor(conclusionId: string): ProvenanceSummary | null {
  return r3.provenance[conclusionId] ?? null;
}

export function adversarialHistoryFor(conclusionId: string): AdversarialHistoryEntry[] {
  return r3.adversarialHistory[conclusionId] ?? [];
}

export function conclusionById(id: string): PublicConclusion | null {
  return bundle.conclusions.find((c) => c.id === id) ?? null;
}
