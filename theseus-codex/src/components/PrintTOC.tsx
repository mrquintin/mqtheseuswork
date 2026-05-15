/**
 * Print-only table of contents for bound / multi-article print views.
 *
 * Each entry is a real in-document anchor link (`<a href="#...">`), so
 * the TOC is clickable in the rendered PDF. `print.css` additionally
 * appends a dotted leader + destination page number to each entry via
 * `target-counter()` in print engines that support paged-media target
 * counters; engines that don't simply render the plain (still
 * clickable) link.
 *
 * This is the React mirror of `_render_toc` in
 * `noosphere/noosphere/docgen/articles_export.py` — keep the anchor
 * scheme (`art-<slug>`) in step with that module so the two paths
 * produce interchangeable documents.
 *
 * Hidden on screen by `.print-only`.
 */
export type PrintTOCEntry = {
  /**
   * In-document anchor id of the target article, *without* the
   * leading `#` (e.g. "art-alpha"). Must match the `id` on the
   * corresponding article element.
   */
  anchor: string;
  /** Article title shown for the entry. */
  title: string;
  /** Optional trailing note, e.g. the publication date. */
  meta?: string | null;
};

export default function PrintTOC({
  entries,
  heading = "Contents",
}: {
  entries: PrintTOCEntry[];
  heading?: string;
}) {
  if (!entries.length) return null;
  return (
    <nav
      aria-hidden="true"
      className="print-only print-toc"
      data-testid="print-toc"
    >
      <h2>{heading}</h2>
      <ol>
        {entries.map((entry, idx) => (
          <li data-testid="print-toc-entry" key={`${entry.anchor}:${idx}`}>
            <a href={`#${entry.anchor}`}>{entry.title}</a>
            {entry.meta ? (
              <span className="print-toc-meta"> ({entry.meta})</span>
            ) : null}
          </li>
        ))}
      </ol>
    </nav>
  );
}
