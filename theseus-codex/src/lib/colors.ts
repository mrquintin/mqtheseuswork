/**
 * Shared color utilities for verdict and status displays.
 * Values reference CSS custom properties defined in the global
 * stylesheet (`var(--gold)`, `var(--ember)`, etc.).
 */

/** Peer-review verdicts: endorse | challenge | abstain */
export function peerVerdictColor(verdict: string): string {
  switch (verdict) {
    case "endorse":
      return "var(--gold)";
    case "challenge":
      return "var(--ember)";
    case "abstain":
    default:
      return "var(--parchment-dim)";
  }
}

/** Coherence-review verdicts: cohere | contradict | unresolved */
export function coherenceVerdictColor(verdict: string): string {
  switch (verdict) {
    case "cohere":
      return "var(--amber)";
    case "contradict":
      return "var(--ember)";
    case "unresolved":
    default:
      return "var(--parchment-dim)";
  }
}

/** Decay status: healthy | decaying | expired */
export function decayStatusColor(status: string): string {
  switch (status) {
    case "healthy":
      return "var(--gold)";
    case "decaying":
      return "var(--parchment)";
    case "expired":
      return "var(--ember)";
    default:
      return "var(--parchment-dim)";
  }
}

/** Peer-review finding severity: blocker | major | minor | info */
export function severityColor(severity: string): string {
  switch (severity) {
    case "blocker":
      return "var(--ember)";
    case "major":
      return "var(--amber)";
    case "minor":
      return "var(--parchment)";
    default:
      return "var(--parchment-dim)";
  }
}

/** Objection severity rubric label: high | medium | low */
export function objectionSeverityColor(label: string): string {
  switch (label) {
    case "high":
      return "var(--ember)";
    case "medium":
      return "var(--amber)";
    case "low":
      return "var(--parchment-dim)";
    default:
      return "var(--parchment-dim)";
  }
}

/** Map rubric severity rank for sorting: high(2) > medium(1) > low(0). */
export function objectionSeverityRank(label: string): number {
  switch (label) {
    case "high":
      return 2;
    case "medium":
      return 1;
    default:
      return 0;
  }
}
