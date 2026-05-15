import Pill, { type PillProps } from "./Pill";
import {
  epistemicTone,
  EPISTEMIC_STATUS,
  type EpistemicStatus,
} from "@/lib/design/tokens";

/**
 * StatusPill — the only sanctioned filled Pill on list / feed surfaces.
 * Per R-002 the filled Pill variant is reserved for epistemic status:
 * one of `{draft, provisional, published, retired}`. Non-status axes
 * (severity, freshness, calibration band, attribution) must render
 * through `<SmallCapsLabel>` or `<NumericBadge>` instead.
 */
export type StatusPillProps = {
  status: EpistemicStatus;
  variant?: "outline" | "filled";
  size?: PillProps["size"];
  label?: string;
};

const LABELS: Record<EpistemicStatus, string> = {
  draft: "Draft",
  provisional: "Provisional",
  published: "Published",
  retired: "Retired",
};

export default function StatusPill({
  status,
  variant = "filled",
  size = "sm",
  label,
}: StatusPillProps) {
  return (
    <Pill
      tone={epistemicTone[status]}
      variant={variant}
      size={size}
      data-epistemic-status={status}
    >
      {label ?? LABELS[status]}
    </Pill>
  );
}

export { EPISTEMIC_STATUS };
export type { EpistemicStatus };
