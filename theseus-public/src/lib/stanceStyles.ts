import type { Stance } from "./currentsTypes";

export const STANCE_LABEL: Record<Stance, string> = {
  agrees: "aligns with firm view",
  disagrees: "contradicts firm view",
  complicates: "complicates firm view",
  insufficient: "insufficient sources",
};

export const STANCE_COLOR: Record<Stance, string> = {
  agrees: "var(--stance-agrees)",
  disagrees: "var(--stance-disagrees)",
  complicates: "var(--stance-complicates)",
  insufficient: "var(--stance-insufficient)",
};

export function confidenceBand(conf: number): "low" | "medium" | "high" {
  if (conf < 0.4) return "low";
  if (conf < 0.75) return "medium";
  return "high";
}
