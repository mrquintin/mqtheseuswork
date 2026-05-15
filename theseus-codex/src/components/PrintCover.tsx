/**
 * Print-only cover page for bound / multi-article print views.
 *
 * The single-article print path uses `PrintMetadataBlock` as its
 * title page; a *bound* run (several articles in one document) instead
 * opens with this cover, so the firm's printed output reads as one
 * deliberate volume rather than a stack of stapled articles. The
 * component is the React mirror of `_render_cover` in
 * `noosphere/noosphere/docgen/articles_export.py` — keep the two
 * shapes in step.
 *
 * Hidden on screen by `.print-only`; `print.css` gives `.print-cover`
 * `page-break-after: always`, so it owns page 1. Because it is page 1,
 * `@page :first` suppresses the running header + footer on it
 * automatically — numbering starts on the page after the cover.
 */
export type PrintCoverProps = {
  /** Volume title, e.g. "Theseus Codex — Bound Articles". */
  title: string;
  /** Optional second line, e.g. the publish window. */
  subtitle?: string | null;
  /** Imprint line above the title. Defaults to "Theseus Codex". */
  imprint?: string;
  /** ISO timestamp the bundle was generated; rendered as a date. */
  generatedAt?: string | null;
  /** Number of articles bound into the volume. */
  articleCount?: number | null;
};

function isoToHumanDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function PrintCover(props: PrintCoverProps) {
  const imprint = props.imprint?.trim() || "Theseus Codex";
  const metaLines: string[] = [];
  if (props.articleCount !== null && props.articleCount !== undefined) {
    const n = props.articleCount;
    metaLines.push(`${n} ${n === 1 ? "article" : "articles"}`);
  }
  if (props.generatedAt) {
    metaLines.push(`Compiled ${isoToHumanDate(props.generatedAt)}`);
  }
  return (
    <section
      aria-hidden="true"
      className="print-only print-cover"
      data-testid="print-cover"
    >
      <p className="print-cover-imprint">{imprint}</p>
      <h1 className="print-cover-title">{props.title}</h1>
      {props.subtitle ? (
        <p className="print-cover-subtitle">{props.subtitle}</p>
      ) : null}
      {metaLines.length ? (
        <div className="print-cover-meta">
          {metaLines.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
