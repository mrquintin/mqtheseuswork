import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { color, radius, space } from "@/lib/design/tokens";

/**
 * Card — bordered surface for grouped content. Wraps the existing
 * `.portal-card` / `.public-card` / `EdgeBadge` wrapper styles, which were
 * each hand-rolled with the same recipe:
 *
 *   background = stone-light  (or rgba amber tint for accented cards)
 *   border     = 1px solid var(--border)  (or amber-dim for accented)
 *   radius     = 2-6px
 *   padding    = 1rem | 1.5rem
 *
 * For *page panels* (header + body + actions), reach for `Panel` instead;
 * Card is the un-headered container.
 */
export type CardTone = "neutral" | "accent" | "warning";
export type CardPadding = "sm" | "md" | "lg";

const TONE_STYLE: Record<CardTone, { background: string; borderColor: string }> = {
  neutral: { background: color.stoneLight, borderColor: color.border },
  accent: {
    background: "color-mix(in srgb, var(--amber) 6%, transparent)",
    borderColor: color.amberDim,
  },
  warning: {
    background: "color-mix(in srgb, var(--ember) 6%, transparent)",
    borderColor: color.ember,
  },
};

const PADDING_STYLE: Record<CardPadding, string> = {
  sm: space.md,
  md: space.lg,
  lg: space["2xl"],
};

export type CardProps = HTMLAttributes<HTMLElement> & {
  tone?: CardTone;
  padding?: CardPadding;
  as?: "div" | "section" | "article" | "aside";
  children: ReactNode;
};

export default function Card({
  tone = "neutral",
  padding = "md",
  as = "div",
  children,
  style,
  ...rest
}: CardProps) {
  const Tag = as;
  const palette = TONE_STYLE[tone];
  const merged: CSSProperties = {
    background: palette.background,
    border: `1px solid ${palette.borderColor}`,
    borderRadius: radius.panel,
    padding: PADDING_STYLE[padding],
    ...style,
  };
  return (
    <Tag {...rest} data-tone={tone} style={merged}>
      {children}
    </Tag>
  );
}
