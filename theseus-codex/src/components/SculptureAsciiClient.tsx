"use client";

/**
 * Client-side dynamic wrapper for `SculptureAscii`. Same pattern as
 * `DashboardHearthClient` / `UploadScrollClient`: the component fetches
 * a mesh + uses DOM-only rendering, so we exclude it from SSR entirely.
 */

import dynamic from "next/dynamic";
import type { SculptureAsciiProps } from "./SculptureAscii";

const SculptureAscii = dynamic(() => import("./SculptureAscii"), {
  ssr: false,
  loading: () => (
    <div
      aria-hidden="true"
      style={{
        minHeight: "120px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: "0.6rem",
        letterSpacing: "0.2em",
        color: "var(--amber-dim)",
        textTransform: "uppercase",
      }}
    >
      Summoning marble…
    </div>
  ),
});

export default function SculptureAsciiClient(props: SculptureAsciiProps) {
  return <SculptureAscii {...props} />;
}
