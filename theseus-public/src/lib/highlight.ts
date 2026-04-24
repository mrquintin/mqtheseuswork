import React from "react";

// Returns the haystack as React nodes with the first case-insensitive,
// whitespace-normalized occurrence of `needle` wrapped in a <mark>. Never
// uses innerHTML — slices are passed as plain text children. If no match is
// found, the original haystack string is returned unchanged.
export function highlightFirst(
  haystack: string,
  needle: string,
): React.ReactNode {
  if (!needle || !haystack) return haystack;
  // Normalize: lowercase, collapse any whitespace run to a single space.
  const normalize = (s: string) => s.toLowerCase().replace(/\s+/g, " ");
  const hayNorm = normalize(haystack);
  const needleNorm = normalize(needle).trim();
  if (!needleNorm) return haystack;
  const idx = hayNorm.indexOf(needleNorm);
  if (idx < 0) return haystack;

  // Map normalized idx back to an original-string offset. Walk the haystack
  // tracking a normalized-position counter; each run of whitespace
  // contributes a single normalized character.
  let origStart = -1;
  {
    let pos = 0;
    let i = 0;
    while (i < haystack.length) {
      if (pos === idx) {
        origStart = i;
        break;
      }
      const ch = haystack[i];
      if (/\s/.test(ch)) {
        while (i < haystack.length && /\s/.test(haystack[i])) i++;
        pos += 1;
      } else {
        i++;
        pos += 1;
      }
    }
    if (origStart < 0 && pos === idx) origStart = i;
  }
  if (origStart < 0) return haystack;

  // Advance origEnd until we've consumed needleNorm.length normalized chars.
  let origEnd = origStart;
  let pos = 0;
  while (origEnd < haystack.length && pos < needleNorm.length) {
    const ch = haystack[origEnd];
    if (/\s/.test(ch)) {
      while (origEnd < haystack.length && /\s/.test(haystack[origEnd])) origEnd++;
      pos += 1;
    } else {
      origEnd++;
      pos += 1;
    }
  }

  return React.createElement(
    React.Fragment,
    null,
    haystack.slice(0, origStart),
    React.createElement(
      "mark",
      {
        style: {
          background: "var(--currents-gold-glow)",
          color: "var(--currents-parchment)",
          padding: "0 0.15rem",
          borderRadius: 1,
        },
      },
      haystack.slice(origStart, origEnd),
    ),
    haystack.slice(origEnd),
  );
}
