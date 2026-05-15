import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import { color, fontSize, radius, space, tracking } from "@/lib/design/tokens";

/**
 * SignalCard (R-013) — pixel-stable primitive for dashboard signal
 * cards. Provides:
 *   • a Cinzel title with the canonical amber-deep hairline
 *   • a right-aligned IBM Plex Mono count
 *   • an optional one-line caption (parchment-dim)
 *   • an optional `footer` link rendered in the `quiet` action variant
 *
 * All dashboard cards should route through this primitive so that
 * sub-layouts (rule placement, count font, footer-link case) cannot
 * drift independently per card.
 */
export type SignalCardProps = {
  title: ReactNode;
  count?: ReactNode;
  caption?: ReactNode;
  footer?: { href: string; label: ReactNode } | ReactNode;
  children?: ReactNode;
  ariaLabel?: string;
};

const headerStyle: CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: space.md,
  borderBottom: `1px solid ${color.amberDeep}`,
  paddingBottom: space.sm,
};

const titleStyle: CSSProperties = {
  fontFamily: "'Cinzel', 'Palatino Linotype', serif",
  fontSize: fontSize.h3,
  fontWeight: 500,
  letterSpacing: tracking.normal,
  color: color.parchment,
  margin: 0,
};

const countStyle: CSSProperties = {
  fontFamily: "'IBM Plex Mono', 'JetBrains Mono', Menlo, monospace",
  fontFeatureSettings: '"tnum" 1',
  fontSize: fontSize.h3,
  color: color.amber,
  textAlign: "right",
  whiteSpace: "nowrap",
};

const captionStyle: CSSProperties = {
  marginTop: space.xs,
  color: color.parchmentDim,
  fontFamily: "'EB Garamond', Georgia, serif",
  fontSize: fontSize.small,
  lineHeight: 1.5,
};

const bodyStyle: CSSProperties = {
  marginTop: space.md,
};

const footerStyle: CSSProperties = {
  marginTop: space.lg,
  paddingTop: space.sm,
  borderTop: `1px solid ${color.border}`,
};

const footerLinkStyle: CSSProperties = {
  display: "inline-block",
  fontFamily: "'Cinzel', 'Palatino Linotype', serif",
  fontSize: fontSize.micro,
  letterSpacing: tracking.widest,
  textTransform: "uppercase",
  color: color.amber,
  textDecoration: "none",
};

const cardStyle: CSSProperties = {
  background: color.stoneLight,
  border: `1px solid ${color.border}`,
  borderRadius: radius.panel,
  padding: space.lg,
};

export default function SignalCard({
  title,
  count,
  caption,
  footer,
  children,
  ariaLabel,
}: SignalCardProps) {
  return (
    <section
      data-component="signal-card"
      aria-label={typeof ariaLabel === "string" ? ariaLabel : undefined}
      style={cardStyle}
    >
      <header style={headerStyle}>
        <h3 style={titleStyle}>{title}</h3>
        {count != null ? (
          <span data-role="count" style={countStyle}>
            {count}
          </span>
        ) : null}
      </header>
      {caption ? <p style={captionStyle}>{caption}</p> : null}
      {children ? <div style={bodyStyle}>{children}</div> : null}
      {footer ? (
        <footer style={footerStyle}>
          {isLinkFooter(footer) ? (
            <Link href={footer.href} style={footerLinkStyle}>
              {footer.label}
            </Link>
          ) : (
            footer
          )}
        </footer>
      ) : null}
    </section>
  );
}

function isLinkFooter(
  footer: SignalCardProps["footer"],
): footer is { href: string; label: ReactNode } {
  return (
    typeof footer === "object" &&
    footer !== null &&
    "href" in footer &&
    typeof (footer as { href?: unknown }).href === "string"
  );
}
