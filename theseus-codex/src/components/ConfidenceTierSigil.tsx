import type { CSSProperties } from "react";

/**
 * Static ASCII sigil for a conclusion's confidence tier.
 *
 * Tier taxonomy (see prisma/schema.prisma):
 *   - firm     : beliefs the firm will bet on. Sigil = solid stacked block.
 *   - founder  : single-founder conviction, not yet firm-wide. Sigil =
 *                rising tetrahedron silhouette.
 *   - open     : unresolved, under active coherence tension. Sigil =
 *                interlocking ring / spiral suggesting an unclosed loop.
 *   - retired  : formerly held, now retracted. Sigil = fractured block.
 *
 * These are small character-art compositions, not live 3D projections,
 * because they appear inline in dense lists (every conclusion card) and
 * need to be very cheap to render. The animated Platonic-solid sigils
 * from `<AsciiSigil />` are used elsewhere for page-header accents where
 * motion is affordable.
 *
 * Each sigil is 3×2 characters — compact enough to sit between a
 * metadata line and a title without dominating. Colour is pulled from
 * CSS custom properties so theme switches propagate.
 */

export type ConfidenceTier = "firm" | "founder" | "open" | "retired" | (string & {});

const SIGILS: Record<ConfidenceTier, { lines: string[]; colorVar: string; title: string }> = {
  firm: {
    // Solid stacked block — the firmest figure we can draw in 6 cells.
    // Reads as a weighty cornerstone.
    lines: [
      "▞█▚",
      "▚█▞",
    ],
    colorVar: "var(--amber)",
    title: "Firm — the firm commits",
  },
  founder: {
    // Rising tetrahedron silhouette. The triangle over a base suggests a
    // single founder's conviction rising above flat ground.
    lines: [
      " ◭ ",
      "═══",
    ],
    colorVar: "var(--amber)",
    title: "Founder — a single founder's conviction, not yet firm-wide",
  },
  open: {
    // Unclosed loop. `∞` with a gap — the tension isn't resolved.
    lines: [
      "╭─╮",
      "╰⋯╯",
    ],
    colorVar: "var(--amber-dim)",
    title: "Open — an unresolved coherence tension",
  },
  retired: {
    // Fractured block. The break suggests a belief that was held, then
    // broken by later evidence or revision.
    lines: [
      "▞▚▞",
      "× ×",
    ],
    colorVar: "var(--parchment-dim)",
    title: "Retired — a belief the firm formerly held",
  },
};

/** Fallback for an unrecognised tier string. Renders a quiet placeholder
 *  rather than an error so DB drift doesn't break the UI. */
const UNKNOWN = {
  lines: [" · ", " · "],
  colorVar: "var(--parchment-dim)",
  title: "Unrecognised tier",
};

export type ConfidenceTierSigilProps = {
  tier: ConfidenceTier;
  /** Font size for the sigil text. Default 0.7rem suits inline card use. */
  size?: string;
  /** Optional surrounding container style (e.g. to control margins). */
  style?: CSSProperties;
  /** Accessible title override. */
  title?: string;
};

export default function ConfidenceTierSigil({
  tier,
  size = "0.7rem",
  style,
  title,
}: ConfidenceTierSigilProps) {
  const spec = (SIGILS as Record<string, typeof SIGILS.firm>)[tier] ?? UNKNOWN;
  return (
    <span
      className="mono"
      role="img"
      aria-label={title ?? spec.title}
      title={title ?? spec.title}
      style={{
        display: "inline-flex",
        flexDirection: "column",
        lineHeight: 1,
        fontSize: size,
        color: spec.colorVar,
        letterSpacing: "0.05em",
        textShadow: "0 0 4px rgba(233, 163, 56, 0.25)",
        ...style,
      }}
    >
      {spec.lines.map((l, i) => (
        <span key={i} style={{ whiteSpace: "pre" }}>
          {l}
        </span>
      ))}
    </span>
  );
}
