import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { color, fontSize, space, tracking } from "@/lib/design/tokens";

/**
 * EmptyState — the "nothing here yet" line. Lifted from the italic
 * "No items need review." pattern in `AttentionQueue` and the equivalent
 * empty-string placeholders sprinkled across `ProvenancePanel`,
 * `MethodTabs`, and `DriftPanel`. Encourages a consistent voice for
 * empties so each surface doesn't reinvent its own copy style.
 *
 * Use `kicker` for an uppercase label above the message (e.g. "queue
 * empty"); use `hint` for a quiet follow-up below.
 */
export type EmptyStateProps = HTMLAttributes<HTMLDivElement> & {
  kicker?: string;
  title?: ReactNode;
  hint?: ReactNode;
  /** Single primary action (button or link). */
  action?: ReactNode;
  children?: ReactNode;
};

export default function EmptyState({
  kicker,
  title,
  hint,
  action,
  children,
  style,
  ...rest
}: EmptyStateProps) {
  const merged: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: space.sm,
    color: color.parchment,
    fontFamily: "'EB Garamond', serif",
    fontStyle: "italic",
    margin: 0,
    ...style,
  };
  return (
    <div {...rest} role={rest.role ?? "status"} style={merged}>
      {kicker ? (
        <span
          className="mono"
          style={{
            color: color.parchmentDim,
            fontSize: fontSize.micro,
            fontStyle: "normal",
            letterSpacing: tracking.widest,
            textTransform: "uppercase",
          }}
        >
          {kicker}
        </span>
      ) : null}
      {title ? <p style={{ margin: 0, color: color.parchment }}>{title}</p> : null}
      {children}
      {hint ? (
        <p
          style={{
            margin: 0,
            color: color.parchmentDim,
            fontStyle: "normal",
            fontSize: fontSize.small,
          }}
        >
          {hint}
        </p>
      ) : null}
      {action ? <div style={{ marginTop: space.xs }}>{action}</div> : null}
    </div>
  );
}
