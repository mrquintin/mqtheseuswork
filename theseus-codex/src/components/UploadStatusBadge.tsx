import {
  PULSING_STATUSES,
  STATUS_COLOR,
  STATUS_LABEL,
  STATUS_TOOLTIP,
  normalizeStatus,
} from "@/lib/uploadStatus";

/**
 * Small pill that shows an Upload's pipeline stage. Pure server
 * component — no state, no JS. Non-terminal stages get a pulsing dot
 * (animation keyframes injected inline as a `<style>` tag so we don't
 * depend on a global class being present in globals.css).
 */
export default function UploadStatusBadge({ status }: { status: string }) {
  const s = normalizeStatus(status);
  const color = STATUS_COLOR[s];
  const label = STATUS_LABEL[s];
  const tooltip = STATUS_TOOLTIP[s];
  const pulsing = PULSING_STATUSES.has(s);

  return (
    <span
      title={tooltip}
      data-status={s}
      data-pulsing={pulsing ? "1" : "0"}
      className="mono upload-status-badge"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.35rem",
        padding: "0.12rem 0.55rem",
        borderRadius: "2px",
        fontSize: "0.58rem",
        letterSpacing: "0.2em",
        textTransform: "uppercase",
        color,
        // Semi-transparent wash of the same colour — works over both
        // the light parchment cards and the dark backdrop without a
        // second variable per status.
        background: `color-mix(in srgb, ${color} 16%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`,
        flexShrink: 0,
        lineHeight: 1.4,
      }}
    >
      {pulsing ? (
        <span
          aria-hidden="true"
          data-testid="status-pulse-dot"
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: color,
            animation: "upload-status-pulse 1.4s ease-in-out infinite",
          }}
        />
      ) : null}
      {label}
      <style>{`
        @keyframes upload-status-pulse {
          0%, 100% { opacity: 0.35; }
          50% { opacity: 1; }
        }
      `}</style>
    </span>
  );
}
