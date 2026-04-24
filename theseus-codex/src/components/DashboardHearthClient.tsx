"use client";

/**
 * Client wrapper around `DashboardHearth` so the dashboard server page
 * can mount it with `ssr: false` (ASCII sampling depends on the DOM).
 * Same pattern as `DashboardPulseClient.tsx`.
 */

import dynamic from "next/dynamic";
import type { DashboardHearthProps } from "./DashboardHearth";

const DashboardHearth = dynamic(() => import("./DashboardHearth"), {
  ssr: false,
  loading: () => (
    <div
      aria-hidden="true"
      style={{
        minHeight: "160px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: "0.65rem",
        letterSpacing: "0.2em",
        color: "var(--amber-dim)",
        textTransform: "uppercase",
      }}
    >
      Kindling hearth…
    </div>
  ),
});

export default function DashboardHearthClient(props: DashboardHearthProps) {
  return <DashboardHearth {...props} />;
}
