import type { PublicOpinion, Stance } from "./currentsTypes";

export interface FilterState {
  topic: string | null;
  stance: Stance | null;
  q: string | null;
  since: string | null; // ISO 8601 timestamp
  view: "chronological" | "by-topic";
}

export const EMPTY_FILTER: FilterState = {
  topic: null,
  stance: null,
  q: null,
  since: null,
  view: "chronological",
};

export function matches(op: PublicOpinion, f: FilterState): boolean {
  if (f.topic && op.topic_hint !== f.topic) return false;
  if (f.stance && op.stance !== f.stance) return false;
  if (f.since && op.generated_at < f.since) return false;
  if (f.q) {
    const q = f.q.toLowerCase();
    const hay = (op.headline + " " + op.body_markdown).toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

export function filterToParams(f: FilterState): URLSearchParams {
  const p = new URLSearchParams();
  if (f.topic) p.set("topic", f.topic);
  if (f.stance) p.set("stance", f.stance);
  if (f.q) p.set("q", f.q);
  if (f.since) p.set("since", f.since);
  if (f.view !== "chronological") p.set("view", f.view);
  return p;
}

export function paramsToFilter(
  sp: URLSearchParams | Record<string, string | undefined>,
): FilterState {
  const get = (k: string): string | null =>
    sp instanceof URLSearchParams ? sp.get(k) : (sp[k] ?? null);
  const rawView = get("view");
  const view: FilterState["view"] =
    rawView === "by-topic" ? "by-topic" : "chronological";
  const rawStance = get("stance");
  const stance: Stance | null =
    rawStance === "agrees" ||
    rawStance === "disagrees" ||
    rawStance === "complicates" ||
    rawStance === "insufficient"
      ? rawStance
      : null;
  return {
    topic: get("topic") || null,
    stance,
    q: get("q") || null,
    since: get("since") || null,
    view,
  };
}
