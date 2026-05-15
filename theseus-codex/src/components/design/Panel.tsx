import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { color, fontSize, radius, space, tracking } from "@/lib/design/tokens";

/**
 * Panel — Card + a header row with a Cinzel title and optional kicker
 * + trailing actions. Extracted from `AttentionQueue`, `DriftPanel`,
 * `ProvenancePanel`, which each implemented this layout inline.
 *
 * Children render below the header in the panel body. Use the `footer`
 * slot for tuning hints or follow-up notes (mirrors AttentionQueue's
 * `DismissalRateHint`).
 */
export type PanelTone = "neutral" | "accent" | "warning";

const TONE_STYLE: Record<
  PanelTone,
  { background: string; borderColor: string; accent: string }
> = {
  neutral: {
    background: color.stoneLight,
    borderColor: color.border,
    accent: color.parchment,
  },
  accent: {
    background: "color-mix(in srgb, var(--amber) 4%, transparent)",
    borderColor: "color-mix(in srgb, var(--amber) 34%, transparent)",
    accent: color.amber,
  },
  warning: {
    background: "color-mix(in srgb, var(--ember) 5%, transparent)",
    borderColor: color.ember,
    accent: color.ember,
  },
};

export type PanelProps = HTMLAttributes<HTMLElement> & {
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  tone?: PanelTone;
  /** Heading level rendered inside the header (default h2). */
  headingAs?: "h2" | "h3";
  /**
   * Optional count rendered as ` · {count}` after the title. The dot
   * separator and uppercase tracking match `AttentionQueue`'s existing
   * "Review queue · 7" header.
   */
  count?: number;
  children?: ReactNode;
};

export default function Panel({
  title,
  meta,
  actions,
  footer,
  tone = "accent",
  headingAs = "h2",
  count,
  children,
  style,
  ...rest
}: PanelProps) {
  const palette = TONE_STYLE[tone];
  const merged: CSSProperties = {
    background: palette.background,
    border: `1px solid ${palette.borderColor}`,
    borderRadius: radius.panel,
    padding: `${space.lg} ${space.xl}`,
    marginBottom: space["2xl"],
    ...style,
  };
  const Heading = headingAs;

  return (
    <section {...rest} data-tone={tone} style={merged}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: space.lg,
          marginBottom: space.md,
          flexWrap: "wrap",
        }}
      >
        <Heading
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: fontSize.bodyLg,
            letterSpacing: tracking.widest,
            textTransform: "uppercase",
            color: palette.accent,
            margin: 0,
          }}
        >
          {title}
          {typeof count === "number" ? ` · ${count}` : null}
        </Heading>
        {meta || actions ? (
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: space.md,
              flexWrap: "wrap",
            }}
          >
            {meta ? (
              <span
                className="mono"
                style={{
                  fontSize: fontSize.micro,
                  letterSpacing: tracking.ultrawide,
                  textTransform: "uppercase",
                  color: color.parchmentDim,
                }}
              >
                {meta}
              </span>
            ) : null}
            {actions}
          </div>
        ) : null}
      </header>
      {children}
      {footer ? (
        <div
          style={{
            marginTop: space.md,
            paddingTop: space.md,
            borderTop: `1px dashed ${color.amberDim}`,
            fontSize: fontSize.meta,
            color: color.parchmentDim,
          }}
        >
          {footer}
        </div>
      ) : null}
    </section>
  );
}
