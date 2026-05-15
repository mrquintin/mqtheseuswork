import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { color, fontSize, space, tracking } from "@/lib/design/tokens";

/**
 * NumericBadge — fill-less mono badge for numeric metadata
 * (counts, scores, calibration band values, durations). Per R-002,
 * pill fills are reserved for epistemic status; numeric metadata
 * renders through this primitive.
 */
export type NumericBadgeProps = {
  tone?: "neutral" | "muted" | "accent" | "success" | "danger";
  prefix?: ReactNode;
  suffix?: ReactNode;
  children: ReactNode;
} & Omit<HTMLAttributes<HTMLSpanElement>, "color" | "prefix">;

const TONE_FG: Record<NonNullable<NumericBadgeProps["tone"]>, string> = {
  neutral: color.parchment,
  muted: color.parchmentDim,
  accent: color.amber,
  success: color.success,
  danger: color.ember,
};

export default function NumericBadge({
  tone = "neutral",
  prefix,
  suffix,
  children,
  style,
  ...rest
}: NumericBadgeProps) {
  const merged: CSSProperties = {
    display: "inline-flex",
    alignItems: "baseline",
    gap: space.xs,
    color: TONE_FG[tone],
    fontFamily: "'IBM Plex Mono', 'JetBrains Mono', Menlo, monospace",
    fontFeatureSettings: '"tnum" 1, "ss01" 1',
    fontSize: fontSize.meta,
    letterSpacing: tracking.tight,
    lineHeight: 1.2,
    ...style,
  };
  return (
    <span data-component="numeric-badge" data-tone={tone} {...rest} style={merged}>
      {prefix ? <span aria-hidden="true">{prefix}</span> : null}
      {children}
      {suffix ? <span aria-hidden="true">{suffix}</span> : null}
    </span>
  );
}
