"use client";

import { useState } from "react";

/**
 * Truncated text with an expand toggle. Renders inline so it works
 * inside dense list rows without forcing a card to grow.
 */
export default function Excerpt({
  text,
  lines = 2,
  className,
  style,
}: {
  text: string;
  lines?: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  const [open, setOpen] = useState(false);
  if (!text) return null;
  return (
    <div className={className} style={style}>
      <span
        style={
          open
            ? { display: "block" }
            : {
                display: "-webkit-box",
                WebkitLineClamp: lines,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }
        }
      >
        {text}
      </span>
      {text.length > 120 ? (
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setOpen((v) => !v);
          }}
          className="mono"
          style={{
            marginTop: "0.25rem",
            background: "transparent",
            border: 0,
            padding: 0,
            color: "var(--amber-dim)",
            fontSize: "0.6rem",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            cursor: "pointer",
          }}
        >
          {open ? "Show less" : "Show more"}
        </button>
      ) : null}
    </div>
  );
}
