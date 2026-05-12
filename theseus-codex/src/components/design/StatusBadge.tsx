import type { ReactNode } from "react";

/**
 * Quiet status pill for inline metadata: "draft", "live", "pending",
 * "failed". Distinct from the bigger `.badge-*` utility set used by
 * upload processing — those convey workflow state with a stronger
 * border; this one is a thin label.
 */
type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export default function StatusBadge({
  tone = "neutral",
  children,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span className={`status-pill status-pill--${tone}`} title={title}>
      {children}
    </span>
  );
}
