import type {
  AnchorHTMLAttributes,
  CSSProperties,
  HTMLAttributes,
  ReactNode,
} from "react";

import {
  color,
  fontSize,
  radius,
  space,
  tone as toneMap,
  tracking,
  type Tone,
} from "@/lib/design/tokens";

/**
 * Pill — a thin, uppercase, mono chip used for metadata, verdicts, scores,
 * and short labels. Extracted from the repeated pattern in `MqsPill`,
 * `CitationPopover` (verdict pill, standing pill), and the `.public-section-link`
 * styling in `globals.css`.
 *
 * Two visual styles:
 *   variant="outline" — bordered, transparent fill (default; matches MqsPill)
 *   variant="filled"  — solid background, light fg (matches verdict pills)
 *
 * Tone selects the color family; see `tokens.tone`.
 *
 * Pills can render as a `<span>` (default) or `<a>` if `href` is supplied.
 */
export type PillVariant = "outline" | "filled";
export type PillSize = "sm" | "md";

type CommonPillProps = {
  tone?: Tone;
  variant?: PillVariant;
  size?: PillSize;
  children: ReactNode;
  /**
   * Optional override pair. Use only when a feature has a documented reason
   * to deviate (e.g. CitationPopover's per-standing palette is data-driven).
   * Both must be approved CSS variables — see `APPROVED_CSS_VARS`.
   */
  colors?: { fg: string; bg?: string; border?: string };
};

export type PillProps =
  | (CommonPillProps & Omit<HTMLAttributes<HTMLSpanElement>, "color"> & { href?: undefined })
  | (CommonPillProps & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "color"> & { href: string });

function pillStyle(
  variant: PillVariant,
  size: PillSize,
  toneKey: Tone,
  override?: CommonPillProps["colors"],
): CSSProperties {
  const palette = toneMap[toneKey];
  const border = override?.border ?? palette.border;
  const bg =
    override?.bg ??
    (variant === "filled" ? palette.border /* use border color as fill */ : palette.bg);
  // When an override.fg is supplied, honour it in both variants (data-driven
  // pills like CitationPopover's verdict/standing rely on this). Otherwise:
  // filled flips fg to the dark surface so text reads on the amber fill;
  // outline keeps the tone's accent fg.
  const fg = override?.fg ?? (variant === "filled" ? color.stone : palette.fg);

  return {
    display: "inline-flex",
    alignItems: "center",
    gap: space.xs,
    padding: size === "sm" ? `${space.xs} ${space.sm}` : `${space.xs} ${space.md}`,
    border: `1px solid ${border}`,
    borderRadius: radius.pill,
    background: bg,
    color: fg,
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: size === "sm" ? fontSize.micro : fontSize.caption,
    letterSpacing: tracking.widest,
    textTransform: "uppercase",
    textDecoration: "none",
    lineHeight: 1,
  };
}

export default function Pill(props: PillProps) {
  const {
    tone = "neutral",
    variant = "outline",
    size = "md",
    children,
    colors,
    style,
    ...rest
  } = props as CommonPillProps & { style?: CSSProperties; href?: string } & Record<string, unknown>;

  const merged: CSSProperties = { ...pillStyle(variant, size, tone, colors), ...style };

  if (typeof (props as { href?: string }).href === "string") {
    const { href, ...anchorRest } = rest as { href: string } & AnchorHTMLAttributes<HTMLAnchorElement>;
    return (
      <a href={href} {...anchorRest} style={merged} data-tone={tone} data-variant={variant}>
        {children}
      </a>
    );
  }
  return (
    <span
      {...(rest as HTMLAttributes<HTMLSpanElement>)}
      style={merged}
      data-tone={tone}
      data-variant={variant}
    >
      {children}
    </span>
  );
}
