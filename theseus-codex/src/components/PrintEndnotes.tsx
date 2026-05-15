import type { ReactNode } from "react";

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
 * cited inline finds note 3 here). Because the numbering is derived
 * purely from the manifest order — never from render-time state — it
 * is identical across reloads.
 *
 * Layout (`print.css`): source names print in small caps, the
 * source-credibility score sits inline after the name, and each note
 * is kept whole across a page break so a source line never strands.
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
   * Source-credibility score (Round 17 prompt 19) as a 0–100 strip
   * value (`BetaPosterior.score_100`). Rendered inline, right after
   * the source name. `null`/omitted when the source is not in the
   * credibility ledger.
   */
  credibility?: number | null;
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

/** `cred NN/100`, or null when there is no usable score. */
function credibilityLabel(score: number | null | undefined): string | null {
  if (score === null || score === undefined) return null;
  if (!Number.isFinite(score)) return null;
  const clamped = Math.min(100, Math.max(0, score));
  return `cred ${clamped.toFixed(0)}/100`;
}

/**
 * Split a URL into nodes with `<wbr/>` break opportunities after the
 * structural characters (`/ . ? & = -`). This lets a long endnote URL
 * wrap at sensible boundaries instead of overflowing the column or
 * breaking mid-token at an arbitrary letter (`print.css` keeps
 * `word-break: normal` and leans on these hints).
 */
function softBreakUrl(url: string): ReactNode[] {
  const pieces = url.split(/(?<=[/.?&=-])/);
  const out: ReactNode[] = [];
  pieces.forEach((piece, i) => {
    out.push(piece);
    if (i < pieces.length - 1) out.push(<wbr key={`wbr-${i}`} />);
  });
  return out;
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
        {sources.map((s, idx) => {
          const cred = credibilityLabel(s.credibility);
          return (
            <li
              data-testid="print-endnote"
              key={`${s.label}:${s.title}:${idx}`}
            >
              <span className="print-endnote-title">{s.title}</span>
              {s.kind ? (
                <span className="print-endnote-meta"> ({s.kind})</span>
              ) : null}
              {cred ? (
                <span className="print-endnote-cred"> · {cred}</span>
              ) : null}
              {isHttp(s.url) ? (
                <>
                  {" "}
                  <a className="print-endnote-url" href={s.url}>
                    {softBreakUrl(s.url)}
                  </a>
                </>
              ) : null}
              {s.bibliographic ? (
                <div className="print-endnote-url">{s.bibliographic}</div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
