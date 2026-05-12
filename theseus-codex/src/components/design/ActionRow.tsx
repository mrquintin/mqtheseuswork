import type { ReactNode } from "react";

/**
 * Horizontal row of actions (buttons, links). Wraps cleanly on narrow
 * widths and aligns its children to the right by default. The companion
 * CSS (`.action-row`, modifiers `.action-row--start`, `.action-row--between`)
 * lives in `globals.css`.
 */
export default function ActionRow({
  children,
  align = "end",
  gap = "md",
  className,
}: {
  children: ReactNode;
  align?: "start" | "end" | "between";
  gap?: "sm" | "md";
  className?: string;
}) {
  const classes = [
    "action-row",
    align === "start"
      ? "action-row--start"
      : align === "between"
        ? "action-row--between"
        : "",
    gap === "sm" ? "action-row--gap-sm" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
  return <div className={classes}>{children}</div>;
}
