"use client";

import { useCallback } from "react";

/**
 * Client-side blob-URL download. Replaces the old `data:` URI pattern
 * (CSV/JSON payload baked into `<a href>`), which blew past browser URL
 * limits and bloated SSR HTML for any non-trivial export.
 */
export default function DownloadButton({
  data,
  filename,
  mime,
  label,
  className,
  style,
}: {
  data: string;
  filename: string;
  mime: string;
  label: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  const handleClick = useCallback(() => {
    const blob = new Blob([data], { type: `${mime};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [data, filename, mime]);

  return (
    <button type="button" onClick={handleClick} className={className} style={style}>
      {label}
    </button>
  );
}
