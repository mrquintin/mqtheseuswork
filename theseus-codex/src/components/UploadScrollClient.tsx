"use client";

/**
 * Thin dynamic-import wrapper around `UploadScroll`. The parent
 * `UploadForm` is already a client component, so a dynamic import isn't
 * strictly required for SSR-boundary reasons, but the ASCII renderer is
 * heavy enough that deferring it until the dropzone is actually on
 * screen (via chunk splitting) is a real win on first-paint.
 */

import dynamic from "next/dynamic";
import type { UploadScrollProps } from "./UploadScroll";

const UploadScroll = dynamic(() => import("./UploadScroll"), {
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
      Unrolling scroll…
    </div>
  ),
});

export default function UploadScrollClient(props: UploadScrollProps) {
  return <UploadScroll {...props} />;
}
