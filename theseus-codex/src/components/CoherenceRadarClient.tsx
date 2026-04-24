"use client";

import dynamic from "next/dynamic";
import type { ComponentProps } from "react";

// Next 16 forbids `dynamic({ ssr: false })` in server components — the call
// must happen inside a client component. That's what this file is for:
// a thin client boundary that can safely disable SSR for the Three.js-
// powered CoherenceRadar, which can't render server-side (no `document`).
const CoherenceRadar = dynamic(() => import("./CoherenceRadar"), {
  ssr: false,
  loading: () => (
    <div
      style={{
        width: 220,
        height: 220,
        border: "1px dashed var(--border)",
        borderRadius: 4,
      }}
    />
  ),
});

type Props = ComponentProps<typeof import("./CoherenceRadar").default>;

export default function CoherenceRadarClient(props: Props) {
  return <CoherenceRadar {...props} />;
}
