import type { PublicOpinion } from "@/lib/currentsTypes";

export const STANCES = [
  "agrees",
  "disagrees",
  "complicates",
  "abstained",
] as const;

export type StanceFilter = (typeof STANCES)[number];

export const SINCE_PRESETS = ["1h", "6h", "24h", "7d", "all"] as const;

export type SincePreset = (typeof SINCE_PRESETS)[number];

export const VIEW_MODES = ["feed", "clusters"] as const;

export type ViewMode = (typeof VIEW_MODES)[number];

export interface Filter {
  q: string;
  topic: string | null;
  stance: StanceFilter[];
  since: SincePreset;
  view: ViewMode;
}

export const DEFAULT_FILTER: Filter = {
  q: "",
  topic: null,
  stance: [],
  since: "all",
  view: "feed",
};

const stanceSet = new Set<string>(STANCES);
const sinceSet = new Set<string>(SINCE_PRESETS);
const viewSet = new Set<string>(VIEW_MODES);

const sinceMs: Record<Exclude<SincePreset, "all">, number> = {
  "1h": 60 * 60 * 1000,
  "6h": 6 * 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
};

interface SearchParamsLike {
  get(name: string): string | null;
  getAll?(name: string): string[];
  toString?(): string;
}

function toSearchParams(
  searchParams: URLSearchParams | SearchParamsLike | string | null | undefined,
): URLSearchParams {
  if (!searchParams) return new URLSearchParams();
  if (typeof searchParams === "string") return new URLSearchParams(searchParams);
  if (searchParams instanceof URLSearchParams) {
    return new URLSearchParams(searchParams.toString());
  }
  return new URLSearchParams(searchParams.toString?.() || "");
}

function clean(value: string | null | undefined): string {
  return (value || "").trim();
}

export function opinionTopicId(opinion: PublicOpinion): string {
  return (
    clean(opinion.topic_hint) ||
    clean(opinion.event?.topic_hint) ||
    "untagged"
  );
}

export function stanceId(rawStance: string): StanceFilter {
  const normalized = clean(rawStance).toLowerCase();
  if (stanceSet.has(normalized)) return normalized as StanceFilter;
  if (["agree", "support", "supports"].includes(normalized)) return "agrees";
  if (["disagree", "oppose", "opposes", "rejects", "refutes"].includes(normalized)) {
    return "disagrees";
  }
  if (["complicate", "mixed", "qualifies", "qualified"].includes(normalized)) {
    return "complicates";
  }
  if (["abstain", "abstains"].includes(normalized)) return "abstained";
  return "abstained";
}

function parseStances(params: URLSearchParams): StanceFilter[] {
  const rawValues = params
    .getAll("stance")
    .flatMap((value) => value.split(","))
    .map((value) => value.trim())
    .filter(Boolean);
  const seen = new Set<StanceFilter>();
  const stances: StanceFilter[] = [];

  for (const value of rawValues) {
    if (!stanceSet.has(value) || seen.has(value as StanceFilter)) continue;
    seen.add(value as StanceFilter);
    stances.push(value as StanceFilter);
  }

  return stances;
}

export function paramsToFilter(
  searchParams: URLSearchParams | SearchParamsLike | string | null | undefined,
): Filter {
  const params = toSearchParams(searchParams);
  const since = clean(params.get("since"));
  const view = clean(params.get("view"));
  const topic = clean(params.get("topic"));

  return {
    q: clean(params.get("q")),
    topic: topic || null,
    stance: parseStances(params),
    since: sinceSet.has(since) ? (since as SincePreset) : DEFAULT_FILTER.since,
    view: viewSet.has(view) ? (view as ViewMode) : DEFAULT_FILTER.view,
  };
}

export function filterToParams(filter: Filter): URLSearchParams {
  const params = new URLSearchParams();
  const q = clean(filter.q);
  const topic = clean(filter.topic);
  const seenStances = new Set<StanceFilter>();

  if (q) params.set("q", q);
  if (topic) params.set("topic", topic);

  for (const stance of filter.stance) {
    if (!stanceSet.has(stance) || seenStances.has(stance)) continue;
    seenStances.add(stance);
    params.append("stance", stance);
  }

  if (filter.since !== DEFAULT_FILTER.since) params.set("since", filter.since);
  if (filter.view !== DEFAULT_FILTER.view) params.set("view", filter.view);

  return params;
}

function matchesSince(
  opinion: PublicOpinion,
  since: SincePreset,
  now: Date | number,
): boolean {
  if (since === "all") return true;

  const opinionTime = new Date(opinion.generated_at).getTime();
  const nowTime = typeof now === "number" ? now : now.getTime();
  if (!Number.isFinite(opinionTime) || !Number.isFinite(nowTime)) return false;

  return opinionTime >= nowTime - sinceMs[since];
}

export function matches(
  opinion: PublicOpinion,
  filter: Filter,
  now: Date | number = Date.now(),
): boolean {
  const query = clean(filter.q).toLowerCase();
  const topic = opinionTopicId(opinion);
  const selectedTopic = clean(filter.topic);

  if (query) {
    const haystack = [
      opinion.headline,
      opinion.body_markdown,
      topic,
      opinion.topic_hint || "",
      opinion.event?.topic_hint || "",
    ]
      .join(" ")
      .toLowerCase();

    if (!haystack.includes(query)) return false;
  }

  if (selectedTopic && topic !== selectedTopic) return false;
  if (filter.stance.length && !filter.stance.includes(stanceId(opinion.stance))) {
    return false;
  }

  return matchesSince(opinion, filter.since, now);
}

export function hasActiveMatchFilter(filter: Filter): boolean {
  return Boolean(
    clean(filter.q) ||
      clean(filter.topic) ||
      filter.stance.length ||
      filter.since !== DEFAULT_FILTER.since,
  );
}
