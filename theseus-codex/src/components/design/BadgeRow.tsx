import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { space } from "@/lib/design/tokens";

/**
 * BadgeRow — horizontal row of pills / badges with wrap. Captures the
 * recurring "list of small chips with a consistent gap" pattern seen in
 * `EdgeBadge`, `CitationPopover` (verdict + standing + reason),
 * `DomainBoundBadge`, and `SwarmDisagreementBadge` callers.
 *
 * This is layout-only. The badges themselves should be `Pill`s (or any
 * inline element); BadgeRow does not impose visuals on its children.
 */
export type BadgeRowAlign = "start" | "center" | "end" | "between";
export type BadgeRowGap = "xs" | "sm" | "md";

const GAP: Record<BadgeRowGap, string> = {
  xs: space.xs,
  sm: space.sm,
  md: space.md,
};

const JUSTIFY: Record<BadgeRowAlign, CSSProperties["justifyContent"]> = {
  start: "flex-start",
  center: "center",
  end: "flex-end",
  between: "space-between",
};

export type BadgeRowProps = HTMLAttributes<HTMLDivElement> & {
  align?: BadgeRowAlign;
  gap?: BadgeRowGap;
  children: ReactNode;
};

export default function BadgeRow({
  align = "start",
  gap = "sm",
  children,
  style,
  ...rest
}: BadgeRowProps) {
  const merged: CSSProperties = {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: GAP[gap],
    justifyContent: JUSTIFY[align],
    ...style,
  };
  return (
    <div {...rest} style={merged}>
      {children}
    </div>
  );
}
