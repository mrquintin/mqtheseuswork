import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { color, radius, space } from "@/lib/design/tokens";

/**
 * Toolbar — a horizontal container for filter/action controls that sits
 * above a content surface (table, list, canvas). Extracted from the
 * inline toolbar layouts in `ExplorerToolbar`, `MethodTabs`, and the
 * `TemporalReplayBar` chrome.
 *
 * The toolbar has three logical zones — `leading`, `center`, and
 * `trailing` (children render in `center`). All children share the same
 * inline-flex row and wrap on narrow widths.
 */
export type ToolbarDensity = "tight" | "comfortable";

export type ToolbarProps = HTMLAttributes<HTMLDivElement> & {
  leading?: ReactNode;
  trailing?: ReactNode;
  density?: ToolbarDensity;
  bordered?: boolean;
  children?: ReactNode;
};

export default function Toolbar({
  leading,
  trailing,
  density = "comfortable",
  bordered = true,
  children,
  style,
  ...rest
}: ToolbarProps) {
  const merged: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: space.md,
    flexWrap: "wrap",
    padding:
      density === "tight" ? `${space.xs} ${space.md}` : `${space.md} ${space.lg}`,
    border: bordered ? `1px solid ${color.border}` : "none",
    borderRadius: bordered ? radius.hairline : 0,
    background: color.stoneLight,
    ...style,
  };
  return (
    <div role="toolbar" {...rest} style={merged}>
      {leading ? (
        <div style={{ display: "flex", alignItems: "center", gap: space.sm }}>
          {leading}
        </div>
      ) : null}
      {children ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: space.md,
            flex: "1 1 auto",
            flexWrap: "wrap",
          }}
        >
          {children}
        </div>
      ) : null}
      {trailing ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: space.sm,
            marginLeft: "auto",
          }}
        >
          {trailing}
        </div>
      ) : null}
    </div>
  );
}
