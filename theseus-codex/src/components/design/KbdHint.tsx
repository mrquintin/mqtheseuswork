import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { color, fontSize, radius, space, tracking } from "@/lib/design/tokens";

/**
 * KbdHint — small inline keyboard hint, like `⌘K` or `Esc`. Extracted
 * from the repeated `<kbd>`-style chips in `CommandPalette`,
 * `KeymapHelp`, `KeyboardChrome`, and the dashboard keymap row.
 *
 * Renders as a semantic `<kbd>` so screen readers announce it as a
 * keyboard input. Combine multiple `KbdHint`s with `+` for chord
 * shortcuts (e.g. `<KbdHint>⌘</KbdHint> + <KbdHint>K</KbdHint>`).
 */
export type KbdHintProps = HTMLAttributes<HTMLElement> & {
  children: ReactNode;
  size?: "sm" | "md";
};

export default function KbdHint({
  children,
  size = "sm",
  style,
  ...rest
}: KbdHintProps) {
  const merged: CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: size === "sm" ? "1.25rem" : "1.5rem",
    padding: size === "sm" ? `0 ${space.xs}` : `${space.xs} ${space.sm}`,
    border: `1px solid ${color.amberDim}`,
    borderBottomWidth: "2px",
    borderRadius: radius.hairline,
    background: color.stoneMid,
    color: color.parchment,
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: size === "sm" ? fontSize.micro : fontSize.caption,
    letterSpacing: tracking.wide,
    lineHeight: 1.4,
    textTransform: "none",
    ...style,
  };
  return (
    <kbd {...rest} style={merged}>
      {children}
    </kbd>
  );
}
