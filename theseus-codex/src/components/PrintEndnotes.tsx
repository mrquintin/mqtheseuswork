/**
 * Print-only endnotes block.
 *
 * On screen the article shows citations as inline popovers (see
 * `CitationPopover.tsx`) — great for reading, useless on paper. When
 * printing, those same citations need to read as numbered endnotes
 * with the full bibliographic information visible at the bottom of the
 * article.
 *
 * Numbering is stable and matches the order of the underlying citation
 * manifest used by the on-screen popovers (so a reader who saw "[3]"
 * cited inline finds note 3 here).
 *
 * Endnotes hyperlink (in PDF) when the underlying source has a public
 * URL. Internal-only sources render as plain text without a link, so
 * private URLs cannot leak into a printed document.
 */
export type PrintEndnoteSource = {
  /** Stable label used by the inline popover (e.g. "S1", "S2"…). */
  label: string;
  /** Title or quoted span — the human-readable identifier of the source. */
  title: string;
  /** Source kind, e.g. "opinion", "forecast", "current event". */
  kind?: string | null;
  /** Public URL if the source is externally addressable; otherwise null. */
  url?: string | null;
  /**
   * Optional supplemental block (e.g. APA / BibTeX text) that should be
   * included verbatim under the endnote. We render it as a wrapping
   * monospace span.
   */
  bibliographic?: string | null;
};

function isHttp(url: string | null | undefined): url is string {
  return Boolean(url && /^https?:\/\//i.test(url));
}

export default function PrintEndnotes({
  sources,
  heading = "Endnotes",
}: {
  sources: PrintEndnoteSource[];
  heading?: string;
}) {
  if (!sources.length) return null;
  return (
    <section
      aria-hidden="true"
      className="print-only print-endnotes"
      data-testid="print-endnotes"
    >
      <h2>{heading}</h2>
      <ol>
        {sources.map((s, idx) => (
          <li
            data-testid="print-endnote"
            key={`${s.label}:${s.title}:${idx}`}
          >
            <span className="print-endnote-title">{s.title}</span>
            {s.kind ? (
              <span className="print-endnote-meta"> ({s.kind})</span>
            ) : null}
            {isHttp(s.url) ? (
              <>
                {" "}
                <a className="print-endnote-url" href={s.url}>
                  {s.url}
                </a>
              </>
            ) : null}
            {s.bibliographic ? (
              <div className="print-endnote-url">{s.bibliographic}</div>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
