/**
 * Print-only metadata block.
 *
 * Rendered into the DOM on every public article + conclusion page but
 * hidden on screen by `.print-only` (defined in `app/print.css`). When
 * the reader hits "Save as PDF" / "Print", the block becomes the
 * opening page of the printed document and carries the irreducible
 * context: title, byline, publish date, methodology pill, MQS, and
 * confidence — plus the cryptographic fingerprint and the canonical
 * URL so a printed page can always be traced back to its live source.
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
      <h1 className="print-metadata-title">{props.title}</h1>
      <p className="print-metadata-byline">
        {props.byline} · {isoToHumanDate(props.publishedAt)}
      </p>
      <dl>
        {props.methodology ? (
          <>
            <dt>Method</dt>
            <dd>{props.methodology}</dd>
          </>
        ) : null}
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
        <dt>Signed</dt>
        <dd className="print-metadata-fingerprint">
          {fingerprint ? fingerprint : "(unsigned)"}
        </dd>
        <dt>Source</dt>
        <dd className="print-endnote-url">{props.canonicalUrl}</dd>
      </dl>
    </aside>
  );
}
