"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

export default function TranscriptAnchorClient() {
  const searchParams = useSearchParams();
  const anchor = searchParams.get("anchor");

  useEffect(() => {
    if (!anchor || !anchor.startsWith("chunk-")) return;
    const target = document.getElementById(anchor);
    if (!target) return;

    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.add("chunk-highlight");
    const timer = window.setTimeout(() => {
      target.classList.remove("chunk-highlight");
    }, 4000);

    return () => window.clearTimeout(timer);
  }, [anchor]);

  return null;
}
