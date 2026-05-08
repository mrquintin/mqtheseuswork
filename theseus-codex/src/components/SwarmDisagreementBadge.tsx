/**
 * Diverge badge for the multi-provider peer-review swarm.
 *
 * The badge is rendered next to a provider's review when at least one
 * other provider's objection was judged contradictory by NLI. It
 * intentionally renders nothing when `divergesWith` is empty so a
 * caller can mount it unconditionally inside a list.
 */

type Tone = "diverge" | "monoculture" | "partial";

const TONE_STYLE: Record<
  Tone,
  { fg: string; border: string; bg: string; label: string; title: string }
> = {
  diverge: {
    fg: "var(--ember)",
    border: "var(--ember)",
    bg: "rgba(180, 60, 40, 0.08)",
    label: "diverge",
    title: "Inter-provider disagreement detected (NLI on objection text).",
  },
  monoculture: {
    fg: "var(--gold-dim)",
    border: "var(--gold-dim)",
    bg: "rgba(140, 110, 50, 0.08)",
    label: "monoculture",
    title:
      "Only one LLM provider was available for this swarm; diversity guarantees do not hold.",
  },
  partial: {
    fg: "var(--parchment-dim)",
    border: "var(--parchment-dim)",
    bg: "rgba(120, 120, 120, 0.08)",
    label: "partial",
    title:
      "Swarm did not visit every provider (budget exhausted or a provider errored).",
  },
};

export interface SwarmDisagreementBadgeProps {
  tone?: Tone;
  divergesWith?: string[];
  partialReason?: string;
}

export default function SwarmDisagreementBadge({
  tone,
  divergesWith,
  partialReason,
}: SwarmDisagreementBadgeProps) {
  const resolvedTone: Tone =
    tone ?? (divergesWith && divergesWith.length > 0 ? "diverge" : "diverge");

  if (resolvedTone === "diverge" && (!divergesWith || divergesWith.length === 0)) {
    return null;
  }

  const style = TONE_STYLE[resolvedTone];
  const title =
    resolvedTone === "diverge" && divergesWith && divergesWith.length > 0
      ? `${style.title} Disagrees with: ${divergesWith.join(", ")}.`
      : resolvedTone === "partial" && partialReason
      ? `${style.title} Reason: ${partialReason}.`
      : style.title;

  return (
    <span
      title={title}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.25rem",
        padding: "0.1rem 0.45rem",
        fontSize: "0.55rem",
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: style.fg,
        border: `1px solid ${style.border}`,
        background: style.bg,
        borderRadius: "2px",
      }}
    >
      {style.label}
      {resolvedTone === "diverge" && divergesWith && divergesWith.length > 0 && (
        <span style={{ color: "var(--parchment-dim)" }}>
          vs {divergesWith.join(", ")}
        </span>
      )}
    </span>
  );
}
