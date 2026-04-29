import React from "react";

export function highlightSubstring(text: string, span: string): React.ReactNode {
  if (!span) {
    console.warn("highlightSubstring: missing span");
    return text;
  }

  const start = text.indexOf(span);
  if (start === -1) {
    console.warn("highlightSubstring: span is not a substring of text");
    return text;
  }

  const before = text.slice(0, start);
  const after = text.slice(start + span.length);

  return React.createElement(
    React.Fragment,
    null,
    before,
    React.createElement(
      "mark",
      { className: "currents-source-highlight" },
      span,
    ),
    after,
  );
}
