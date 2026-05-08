"use client";

import { useCallback } from "react";

/**
 * "PDF" toolbar icon. Triggers the browser's native print dialog,
 * which the print stylesheet (`app/print.css`) re-typesets into a
 * print-quality view. The reader hits "Save as PDF" from the dialog;
 * no server-side renderer is needed.
 *
 * The button itself carries the `no-print` class so it never appears
 * in the printed document — it's the only way out of the loop.
 */
export default function PrintButton({
  label = "PDF",
  title = "Save or print this article as PDF",
  className,
  style,
}: {
  label?: string;
  title?: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  const onClick = useCallback(() => {
    if (typeof window !== "undefined") window.print();
  }, []);

  return (
    <button
      aria-label={title}
      className={`no-print ${className ?? ""}`.trim()}
      data-testid="print-button"
      onClick={onClick}
      style={style}
      title={title}
      type="button"
    >
      <span aria-hidden="true" style={{ marginRight: "0.35em" }}>
        ⤓
      </span>
      {label}
    </button>
  );
}
