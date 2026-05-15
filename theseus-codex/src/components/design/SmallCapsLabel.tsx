import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { color, fontSize, space, tracking } from "@/lib/design/tokens";

/**
 * SmallCapsLabel — fill-less inline label for non-status axes
 * (severity, freshness, calibration band, attribution). Per R-002,
 * pill fills are reserved for epistemic status; everything else
 * renders through this primitive or `<NumericBadge>`.
 */
export type SmallCapsLabelProps = {
  tone?: "neutral" | "muted" | "accent";
  children: ReactNode;
} & Omit<HTMLAttributes<HTMLSpanElement>, "color">;

const TONE_FG: Record<NonNullable<SmallCapsLabelProps["tone"]>, string> = {
  neutral: color.parchment,
  muted: color.parchmentDim,
  accent: color.amber,
};

export default function SmallCapsLabel({
  tone = "muted",
  children,
  style,
  ...rest
}: SmallCapsLabelProps) {
  const merged: CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: space.xs,
    color: TONE_FG[tone],
    fontFamily: "'Cinzel', 'Palatino Linotype', serif",
    fontSize: fontSize.micro,
    letterSpacing: tracking.widest,
    textTransform: "uppercase",
    lineHeight: 1.2,
    ...style,
  };
  return (
    <span data-component="small-caps-label" data-tone={tone} {...rest} style={merged}>
      {children}
    </span>
  );
}
