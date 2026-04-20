"use client";

/**
 * Client-side dynamic wrapper around `SculptureBackdrop`. Same rationale
 * as the other `*Client.tsx` wrappers: the backdrop needs the DOM
 * (mesh fetch, canvas, window media query), so we skip SSR entirely and
 * let Next.js code-split it into its own chunk.
 */

import dynamic from "next/dynamic";
import type { SculptureBackdropProps } from "./SculptureBackdrop";

const SculptureBackdrop = dynamic(() => import("./SculptureBackdrop"), {
  ssr: false,
});

export default function SculptureBackdropClient(props: SculptureBackdropProps) {
  return <SculptureBackdrop {...props} />;
}
