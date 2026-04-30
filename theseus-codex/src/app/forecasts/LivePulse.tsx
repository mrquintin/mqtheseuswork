import type { CSSProperties } from "react";

interface LivePulseProps {
  active: boolean;
  color?: string;
  idleColor?: string;
  label?: string;
}

const dotStyle: CSSProperties = {
  borderRadius: "50%",
  display: "inline-block",
  height: "6px",
  width: "6px",
};

export default function LivePulse({
  active,
  color = "var(--forecasts-cool-gold)",
  idleColor = "var(--forecasts-muted)",
  label,
}: LivePulseProps) {
  return (
    <>
      <span
        aria-hidden
        className={active ? "currents-pulse" : undefined}
        style={{
          ...dotStyle,
          background: active ? color : idleColor,
          boxShadow: active ? `0 0 8px ${color}` : "none",
        }}
      />
      {label ? <span>{label}</span> : null}
    </>
  );
}
