/**
 * RetirementBanner — surfaces a method's retirement state.
 *
 * The retirement workflow lives in
 * `noosphere/noosphere/methods/retirement.py`; the Codex DB mirrors the
 * state into `MethodRetirement`. This component renders that state in
 * two places:
 *
 *  - the authed methods registry page (`/methods/[name]/[version]`), and
 *  - the public methodology page (`/methodology/[method]`).
 *
 * It is a plain server component — no client JS — so it works the same
 * with JavaScript disabled.
 *
 * Rendering by state:
 *  - `active`           → renders nothing (a method with a rejected
 *                         review is fully in service; the memo is the
 *                         only record and lives on the noosphere side).
 *  - `under_review`     → an amber "under review" note.
 *  - `deprecated`       → a tombstone card. The method still runs, but
 *                         the firm has accepted its retirement.
 *  - `retired`          → a tombstone card. Calls are refused; the
 *                         method survives only for historical re-analysis.
 *
 * The tombstone styling is deliberate: public readers should be able to
 * see what the firm has stopped trusting. Retired methods do not vanish
 * from the public record.
 */

export type RetirementState =
  | "active"
  | "under_review"
  | "deprecated"
  | "retired";

export interface RetirementInfo {
  state: RetirementState;
  replacement: string | null;
  rationale: string;
  reviewOpenedAt: string | null;
  deprecatedAt: string | null;
  retiredAt: string | null;
  sunsetAt: string | null;
}

function fmtDate(value: string | null): string | null {
  if (!value) return null;
  // Accept both ISO datetimes and bare dates; show the date only.
  return value.slice(0, 10);
}

export default function RetirementBanner({
  info,
  variant = "authed",
}: {
  info: RetirementInfo | null;
  /** `public` slightly softens the copy for outside readers. */
  variant?: "authed" | "public";
}) {
  if (!info || info.state === "active") return null;

  if (info.state === "under_review") {
    const opened = fmtDate(info.reviewOpenedAt);
    return (
      <div
        role="note"
        aria-label="Method under retirement review"
        style={{
          margin: "1rem 0",
          padding: "0.7rem 1rem",
          borderLeft: "3px solid var(--amber, #d4a017)",
          background: "rgba(212, 160, 23, 0.06)",
          fontSize: "0.85rem",
        }}
      >
        <strong
          style={{
            fontFamily: "monospace",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            fontSize: "0.7rem",
            color: "var(--amber, #d4a017)",
          }}
        >
          Under retirement review
        </strong>
        <p style={{ margin: "0.35rem 0 0", color: "var(--parchment-dim, #b8ad95)" }}>
          This method met one or more retirement criteria and is in a
          founder review{opened ? ` opened ${opened}` : ""}.{" "}
          {variant === "public"
            ? "Until the review concludes the method remains in service."
            : "The review will accept (deprecate) or reject (return to active)."}
        </p>
      </div>
    );
  }

  // deprecated | retired → tombstone card.
  const retired = info.state === "retired";
  const accent = retired ? "var(--ember, #c0392b)" : "var(--parchment-dim, #b8ad95)";
  const label = retired ? "Retired method" : "Deprecated method";
  const sunset = fmtDate(info.sunsetAt);
  const deprecated = fmtDate(info.deprecatedAt);
  const retiredAt = fmtDate(info.retiredAt);

  return (
    <div
      role="note"
      aria-label={`${label}: ${label === "Retired method" ? "calls refused" : "scheduled for retirement"}`}
      style={{
        margin: "1rem 0",
        padding: "1rem 1.15rem",
        border: `1px dashed ${accent}`,
        borderLeft: `4px solid ${accent}`,
        // Grayscale wash — the tombstone reads as "out of service" at a
        // glance, even before the text is read.
        background: retired
          ? "rgba(120, 120, 120, 0.10)"
          : "rgba(120, 120, 120, 0.06)",
        filter: retired ? "grayscale(0.35)" : undefined,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "0.5rem",
          flexWrap: "wrap",
        }}
      >
        <span aria-hidden style={{ fontSize: "1rem" }}>
          †
        </span>
        <strong
          style={{
            fontFamily: "monospace",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            fontSize: "0.72rem",
            color: accent,
          }}
        >
          {label}
        </strong>
      </div>

      <p
        style={{
          margin: "0.5rem 0 0",
          fontSize: "0.85rem",
          color: "var(--parchment, #d8cdb0)",
        }}
      >
        {retired ? (
          <>
            The firm has stopped trusting this method. Calls to it are
            refused; it survives only for historical re-analysis of the
            conclusions it already produced.
          </>
        ) : (
          <>
            The firm has accepted this method&apos;s retirement. It still
            runs, but its conclusions are being migrated and it is on a
            sunset timeline.
          </>
        )}
      </p>

      {info.replacement ? (
        <p
          style={{
            margin: "0.5rem 0 0",
            fontSize: "0.85rem",
            color: "var(--parchment, #d8cdb0)",
          }}
        >
          Replaced by{" "}
          <code style={{ color: "var(--gold, #c9a84a)" }}>
            {info.replacement}
          </code>
          .
        </p>
      ) : (
        <p
          style={{
            margin: "0.5rem 0 0",
            fontSize: "0.85rem",
            color: "var(--parchment-dim, #b8ad95)",
          }}
        >
          No replacement was named — conclusions it produced are under
          review for revision or retraction.
        </p>
      )}

      {(deprecated || sunset || retiredAt) && (
        <ul
          style={{
            margin: "0.6rem 0 0",
            paddingLeft: "1.1rem",
            fontSize: "0.75rem",
            color: "var(--parchment-dim, #b8ad95)",
          }}
        >
          {deprecated && <li>Deprecated {deprecated}</li>}
          {sunset && <li>Sunset deadline (reanalysis complete) {sunset}</li>}
          {retiredAt && <li>Retired {retiredAt}</li>}
        </ul>
      )}
    </div>
  );
}
