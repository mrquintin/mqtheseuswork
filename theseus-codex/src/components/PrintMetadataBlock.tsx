/**
 * Print-only metadata block — the printed document's title page.
 *
 * Rendered into the DOM on every public article + conclusion page but
 * hidden on screen by `.print-only` (defined in `app/print.css`). When
 * the reader hits "Save as PDF" / "Print", `print.css` gives this
 * block `page-break-after: always`, so it becomes a true title page:
 * a full opening page carrying the irreducible context — title,
 * author, methodology pill, MQS, confidence, publication date — with
 * the cryptographic fingerprint and canonical URL settled against the
 * page foot so a printed page can always be traced back to its live
 * source. The article body then opens on page 2, which is where the
 * running header + numbered footer begin.
 *
 * The component is intentionally low-styling: the visual rules live in
 * `print.css` so the screen rendering cannot regress.
 */
export type PrintMetadataBlockProps = {
  title: string;
  byline: string;
  publishedAt: string;
  /** Plain-text methodology label (e.g. "Six-layer coherence"). */
  methodology?: string | null;
  /** MQS composite as a 0-1 fraction; rendered as a percentage. */
  mqsComposite?: number | null;
  /** Headline confidence as a 0-1 fraction; rendered as a percentage. */
  confidence?: number | null;
  /** Calibration-discounted confidence label (e.g. "stated 86% / discounted 81%"). */
  confidenceContext?: string | null;
  /**
   * Ed25519 publication-key fingerprint from
   * `/api/public/signature/<slug>`. May be `null` if the publication
   * has not yet been signed; we then say "(unsigned)" so the reader
   * sees the absence rather than a missing field.
   */
  signatureFingerprint?: string | null;
  /** Canonical web URL of this article. */
  canonicalUrl: string;
};

function pct(n?: number | null): string | null {
  if (n === null || n === undefined) return null;
  if (!Number.isFinite(n)) return null;
  const clamped = Math.min(1, Math.max(0, n));
  return `${(clamped * 100).toFixed(0)}%`;
}

function isoToHumanDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function PrintMetadataBlock(props: PrintMetadataBlockProps) {
  const mqsLabel = pct(props.mqsComposite);
  const confidenceLabel = pct(props.confidence);
  const fingerprint = props.signatureFingerprint?.trim();
  return (
    <aside
      aria-hidden="true"
      className="print-only print-metadata-block"
      data-testid="print-metadata-block"
    >
      <p className="print-metadata-imprint">Theseus Codex</p>
      <h1 className="print-metadata-title">{props.title}</h1>
      <p className="print-metadata-byline">{props.byline}</p>
      {props.methodology ? (
        <p className="print-metadata-pill" data-testid="print-metadata-pill">
          {props.methodology}
        </p>
      ) : null}
      <dl className="print-metadata-stats">
        {mqsLabel ? (
          <>
            <dt>MQS</dt>
            <dd>{mqsLabel} composite</dd>
          </>
        ) : null}
        {confidenceLabel ? (
          <>
            <dt>Confidence</dt>
            <dd>
              {confidenceLabel}
              {props.confidenceContext ? ` · ${props.confidenceContext}` : ""}
            </dd>
          </>
        ) : null}
        <dt>Published</dt>
        <dd>{isoToHumanDate(props.publishedAt)}</dd>
      </dl>
      <div className="print-metadata-foot">
        <p className="print-metadata-row">
          <span className="print-metadata-key">Signed</span>
          <span className="print-metadata-fingerprint">
            {fingerprint ? fingerprint : "(unsigned)"}
          </span>
        </p>
        <p className="print-metadata-row">
          <span className="print-metadata-key">Source</span>
          <span className="print-endnote-url">{props.canonicalUrl}</span>
        </p>
      </div>
    </aside>
  );
}
