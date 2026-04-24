import UploadRetryButton from "./UploadRetryButton";

/**
 * Subset of an `Upload` row the detail panel needs — server pages
 * should select at least these fields when preparing data for the
 * dashboard card.
 */
export interface UploadRowDetailItem {
  id: string;
  status: string;
  errorMessage?: string | null;
  extractionMethod?: string | null;
}

/**
 * Inline detail rendered below an upload's title row. Three shapes,
 * depending on status:
 *
 *   * `ingested` with an extractionMethod → one-line muted caption
 *     describing how the text was obtained ("transcribed locally
 *     (faster-whisper)", "OCR'd with ocrmypdf"…)
 *   * `failed`                            → `<details>` collapsible
 *     with a truncated summary and a {@link UploadRetryButton} inside
 *   * anything else                       → renders nothing (pending /
 *     in-flight rows show their state via the badge alone)
 *
 * The detail is deliberately quiet — a founder scanning the dashboard
 * for fresh conclusions shouldn't get a wall of stack traces. The
 * summary truncates at 140 chars; the full message expands on click.
 */
export default function UploadRowDetail({
  upload,
}: {
  upload: UploadRowDetailItem;
}) {
  if (upload.status === "ingested" && upload.extractionMethod) {
    return (
      <div
        className="mono"
        style={{
          fontSize: "0.62rem",
          letterSpacing: "0.12em",
          color: "var(--parchment-dim)",
          marginTop: "0.35rem",
        }}
      >
        {humanMethod(upload.extractionMethod)}
      </div>
    );
  }

  if (upload.status !== "failed") return null;

  const raw = upload.errorMessage ?? "Processing failed with no detail.";
  const summary = truncate(raw, 140);

  return (
    <details style={{ fontSize: "0.82rem", marginTop: "0.4rem" }}>
      <summary
        style={{
          cursor: "pointer",
          color: "var(--ember)",
          lineHeight: 1.4,
        }}
      >
        {summary}
      </summary>
      <pre
        style={{
          whiteSpace: "pre-wrap",
          marginTop: "0.4rem",
          padding: "0.55rem 0.7rem",
          background: "rgba(179, 58, 42, 0.08)",
          border: "1px solid color-mix(in srgb, var(--ember) 35%, transparent)",
          borderRadius: 2,
          fontSize: "0.75rem",
          color: "var(--parchment)",
          lineHeight: 1.45,
          overflowX: "auto",
        }}
      >
        {raw}
      </pre>
      <UploadRetryButton uploadId={upload.id} />
    </details>
  );
}

/**
 * Map noosphere's internal extraction_method tokens to a short
 * founder-facing phrase. Unknown values fall through to a generic
 * "extracted via X" so the UI still communicates that SOMETHING
 * happened even if a new extractor lands before this map is updated.
 */
export function humanMethod(method: string): string {
  const map: Record<string, string> = {
    passthrough: "stored as text",
    "faster-whisper": "transcribed locally (faster-whisper)",
    "openai-whisper-1": "transcribed via OpenAI",
    pypdf: "extracted with pypdf",
    ocrmypdf: "OCR'd with ocrmypdf",
  };
  return map[method] ?? `extracted via ${method}`;
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1).trimEnd() + "…";
}
