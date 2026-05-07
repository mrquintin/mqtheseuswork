"use client";

import { useEffect, useMemo, useRef } from "react";

interface XPostEmbedProps {
  authorHandle?: string | null;
  className?: string;
  compact?: boolean;
  fallbackText?: string | null;
  observedAt?: string | null;
  url: string;
}

type TwitterWidgets = {
  widgets?: {
    load?: (element?: HTMLElement | null) => void;
  };
};

declare global {
  interface Window {
    twttr?: TwitterWidgets;
  }
}

const WIDGET_SCRIPT_ID = "twitter-wjs";
const WIDGET_SRC = "https://platform.twitter.com/widgets.js";

function ensureWidgetsScript(): HTMLScriptElement {
  const existing = document.getElementById(WIDGET_SCRIPT_ID);
  if (existing instanceof HTMLScriptElement) return existing;

  const script = document.createElement("script");
  script.id = WIDGET_SCRIPT_ID;
  script.async = true;
  script.charset = "utf-8";
  script.src = WIDGET_SRC;
  document.body.appendChild(script);
  return script;
}

function embedUrl(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);
    if (url.hostname === "x.com" || url.hostname === "www.x.com") {
      url.hostname = "twitter.com";
    }
    return url.toString();
  } catch {
    return rawUrl;
  }
}

function formatFallbackAt(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function XPostEmbed({
  authorHandle,
  className,
  compact = false,
  fallbackText,
  observedAt,
  url,
}: XPostEmbedProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const normalizedUrl = useMemo(() => embedUrl(url), [url]);
  const handle = authorHandle?.trim();
  const displayHandle = handle
    ? handle.startsWith("@")
      ? handle
      : `@${handle}`
    : "X post";
  const fallbackAt = formatFallbackAt(observedAt);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const render = () => window.twttr?.widgets?.load?.(container);
    if (window.twttr?.widgets?.load) {
      render();
      return;
    }

    const script = ensureWidgetsScript();
    script.addEventListener("load", render);
    return () => script.removeEventListener("load", render);
  }, [normalizedUrl]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        marginBottom: compact ? "0.85rem" : "1.15rem",
        maxWidth: "550px",
      }}
    >
      <blockquote
        className="twitter-tweet"
        data-conversation="none"
        data-dnt="true"
        data-theme="dark"
      >
        <p lang="en" dir="ltr">
          {fallbackText?.trim() || "View this post on X."}
        </p>
        <a href={normalizedUrl} rel="noopener nofollow ugc" target="_blank">
          {displayHandle}
          {fallbackAt ? ` - ${fallbackAt}` : ""}
        </a>
      </blockquote>
    </div>
  );
}
