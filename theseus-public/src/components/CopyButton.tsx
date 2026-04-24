"use client";

import { useState } from "react";

export default function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "copied" | "err">("idle");

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
      setTimeout(() => setState("idle"), 1200);
    } catch {
      setState("err");
      setTimeout(() => setState("idle"), 1500);
    }
  }

  return (
    <button type="button" className="btn" onClick={() => void onCopy()}>
      {state === "copied" ? "Copied" : state === "err" ? "Copy failed" : label}
    </button>
  );
}
