"use client";

import {
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type RefObject,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

import type { PublicCitation } from "@/lib/currentsTypes";
import { renderSafeMarkdown } from "@/lib/safeMarkdown";
import {
  normalizeCredibilityPayload,
  scoreBandColor,
  scoreBandLabel,
  sourceTypeLabel,
  summaryLine,
  unconfidentCaveat,
  type SourceCredibilityPayload,
} from "@/lib/sourceCredibility";
import {
  normalizeVerdictPayload,
  verdictPill,
  verdictSummary,
  type CitationVerdictPayload,
} from "@/lib/citationVerdict";

type CitationWithVisibility = PublicCitation & {
  conclusion_title?: string | null;
  conclusionTitle?: string | null;
  source_visibility?: string | null;
  visibility?: string | null;
  source_standing?: string | null;
  sourceStanding?: string | null;
  standing_reason?: string | null;
  standingReason?: string | null;
  source_credibility?: Partial<SourceCredibilityPayload> | null;
  sourceCredibility?: Partial<SourceCredibilityPayload> | null;
  citation_verdict?: unknown;
  citationVerdict?: unknown;
};

type SourceStanding =
  | "active"
  | "retracted"
  | "corrected"
  | "disputed"
  | "expired";

const STANDING_STYLE: Record<Exclude<SourceStanding, "active">, { bg: string; fg: string; label: string }> = {
  retracted: { bg: "#5b1414", fg: "#ffd1d1", label: "Retracted" },
  corrected: { bg: "#5b3414", fg: "#ffe2c2", label: "Corrected" },
  expired: { bg: "#3a3a3a", fg: "#dcdcdc", label: "Expired" },
  disputed: { bg: "#5a4a14", fg: "#ffe9a8", label: "Disputed" },
};

function normalizedStanding(citation: CitationWithVisibility): SourceStanding {
  const raw = (citation.source_standing ?? citation.sourceStanding ?? "active")
    .toString()
    .trim()
    .toLowerCase();
  if (raw === "retracted" || raw === "corrected" || raw === "disputed" || raw === "expired") {
    return raw;
  }
  return "active";
}

function standingReason(citation: CitationWithVisibility): string {
  return (citation.standing_reason ?? citation.standingReason ?? "").toString().trim();
}

interface CitationPopoverProps {
  open: boolean;
  onClose: () => void;
  anchorRef: RefObject<HTMLElement | null>;
  citation: CitationWithVisibility;
  conclusionText: string;
  publicUrl: string | null;
  id?: string;
}

interface PopoverPosition {
  left: number;
  top: number;
  width: number;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
const ESTIMATED_HEIGHT = 250;
const MARGIN = 12;
const WIDTH = 360;
const POPOVER_Z_INDEX = 10020;

function effectiveWidth(viewportWidth: number): number {
  return Math.min(WIDTH, Math.max(220, viewportWidth - MARGIN * 2));
}

const shellStyle: CSSProperties = {
  background: "var(--currents-bg-elevated)",
  border: "1px solid var(--currents-border)",
  borderRadius: "6px",
  boxShadow: "0 18px 45px rgba(0, 0, 0, 0.38)",
  color: "var(--currents-parchment)",
  maxWidth: `calc(100vw - ${MARGIN * 2}px)`,
  padding: "0.85rem",
  position: "fixed",
  zIndex: POPOVER_Z_INDEX,
};

const captionStyle: CSSProperties = {
  color: "var(--currents-muted)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.68rem",
  letterSpacing: "0.12em",
  textTransform: "uppercase",
};

const titleStyle: CSSProperties = {
  color: "var(--currents-parchment)",
  fontFamily: "'EB Garamond', serif",
  fontSize: "1rem",
  lineHeight: 1.25,
  margin: "0.25rem 0 0",
};

const bodyStyle: CSSProperties = {
  color: "var(--currents-parchment-dim)",
  fontSize: "0.9rem",
  lineHeight: 1.55,
  marginTop: "0.65rem",
  maxHeight: "16rem",
  overflow: "auto",
};

const linkStyle: CSSProperties = {
  color: "var(--currents-gold)",
  display: "inline-flex",
  fontSize: "0.84rem",
  marginTop: "0.7rem",
  textDecoration: "none",
};

const privateNoteStyle: CSSProperties = {
  borderTop: "1px solid var(--currents-border)",
  color: "var(--currents-muted)",
  fontSize: "0.78rem",
  lineHeight: 1.45,
  margin: "0.75rem 0 0",
  paddingTop: "0.6rem",
};

function citationKind(citation: PublicCitation): string {
  const kind = citation.source_kind.trim().toLowerCase();
  if (kind === "claim") return "opinion";
  if (kind === "conclusion") return "firm conclusion";
  return kind || "firm source";
}

function citationTitle(citation: CitationWithVisibility): string {
  return (
    citation.conclusion_title?.trim() ||
    citation.conclusionTitle?.trim() ||
    citationKind(citation)
  );
}

function normalizedVisibility(citation: CitationWithVisibility): string {
  return (citation.source_visibility ?? citation.visibility ?? "")
    .trim()
    .toLowerCase()
    .replace(/-/g, "_");
}

function canExposePublicUrl(citation: CitationWithVisibility, publicUrl: string | null): boolean {
  return Boolean(publicUrl?.trim()) && normalizedVisibility(citation) === "org";
}

function safeHref(rawUrl: string | null): string | null {
  const trimmed = rawUrl?.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("/") && !trimmed.startsWith("//")) return trimmed;
  try {
    const url = new URL(trimmed);
    if (url.protocol === "http:" || url.protocol === "https:") return url.toString();
  } catch {
    return null;
  }
  return null;
}

function isHTMLElement(value: unknown): value is HTMLElement {
  if (!value || typeof value !== "object") return false;
  if (typeof HTMLElement === "undefined") {
    return typeof (value as HTMLElement).focus === "function";
  }
  return value instanceof HTMLElement;
}

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => !element.hasAttribute("disabled") && element.tabIndex !== -1,
  );
}

function anchorIsOutsideViewport(anchor: HTMLElement): boolean {
  const rect = anchor.getBoundingClientRect();
  const viewportWidth =
    window.innerWidth || document.documentElement?.clientWidth || WIDTH;
  const viewportHeight =
    window.innerHeight || document.documentElement?.clientHeight || ESTIMATED_HEIGHT;
  return (
    rect.bottom < 0 ||
    rect.top > viewportHeight ||
    rect.right < 0 ||
    rect.left > viewportWidth
  );
}

function positionFor(anchor: HTMLElement, dialog: HTMLElement | null): PopoverPosition {
  const rect = anchor.getBoundingClientRect();
  const viewportWidth =
    window.innerWidth || document.documentElement?.clientWidth || WIDTH + MARGIN * 2;
  const viewportHeight =
    window.innerHeight || document.documentElement?.clientHeight || ESTIMATED_HEIGHT;
  const width = effectiveWidth(viewportWidth);
  const height = dialog?.offsetHeight || ESTIMATED_HEIGHT;
  const preferredTop = rect.top - height - 10;
  const top =
    preferredTop >= MARGIN
      ? preferredTop
      : Math.min(rect.bottom + 10, Math.max(MARGIN, viewportHeight - height - MARGIN));
  const centeredLeft = rect.left + rect.width / 2 - width / 2;
  const left = Math.min(
    Math.max(MARGIN, centeredLeft),
    Math.max(MARGIN, viewportWidth - width - MARGIN),
  );
  return { left, top, width };
}

interface CitationVerdictPillProps {
  verdict: CitationVerdictPayload;
}

function CitationVerdictPill({ verdict }: CitationVerdictPillProps) {
  const style = verdictPill(verdict.relation_holds);
  const overridden = Boolean(verdict.overridden_by && verdict.override_reason);
  const summary = verdictSummary(verdict);
  return (
    <div
      data-testid="citation-verdict"
      data-verdict={verdict.relation_holds}
      style={{ marginTop: "0.4rem" }}
      title={summary}
    >
      <span
        aria-label={`Citation verdict: ${style.label}`}
        data-testid="citation-verdict-pill"
        style={{
          background: style.bg,
          border: "1px solid rgba(0,0,0,0.35)",
          borderRadius: "999px",
          color: style.fg,
          display: "inline-block",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.65rem",
          letterSpacing: "0.1em",
          padding: "0.15rem 0.55rem",
          textTransform: "uppercase",
        }}
      >
        {style.label}
      </span>
      {overridden ? (
        <span
          style={{
            color: "var(--currents-muted)",
            fontSize: "0.7rem",
            marginLeft: "0.5rem",
          }}
        >
          founder override
        </span>
      ) : null}
      <p
        style={{
          color: "var(--currents-parchment-dim)",
          fontSize: "0.72rem",
          lineHeight: 1.4,
          margin: "0.35rem 0 0",
        }}
      >
        {summary}
      </p>
    </div>
  );
}

interface CredibilityStripProps {
  credibility: SourceCredibilityPayload;
}

function CredibilityStrip({ credibility }: CredibilityStripProps) {
  const score = Math.max(0, Math.min(100, credibility.score_100));
  const fill = scoreBandColor(score);
  const bandLabel = scoreBandLabel(score);
  const summary = summaryLine(credibility);
  const tooltip = credibility.confident
    ? summary
    : `${summary} — ${unconfidentCaveat(credibility)}`;

  return (
    <div
      data-testid="source-credibility"
      style={{
        borderTop: "1px solid var(--currents-border)",
        marginTop: "0.7rem",
        paddingTop: "0.55rem",
      }}
      title={tooltip}
    >
      <div
        style={{
          alignItems: "baseline",
          color: "var(--currents-muted)",
          display: "flex",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.65rem",
          justifyContent: "space-between",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
        }}
      >
        <span>Source credibility</span>
        <span style={{ color: "var(--currents-parchment-dim)" }}>
          {sourceTypeLabel(credibility.source_type)}
        </span>
      </div>
      <div
        aria-label={
          credibility.confident
            ? `Source credibility ${score} of 100 (${bandLabel})`
            : `Source credibility unsettled — ${credibility.n_updates} of ${credibility.min_updates_for_confidence} updates`
        }
        role="img"
        style={{
          background: "rgba(255,255,255,0.06)",
          borderRadius: "3px",
          height: "8px",
          marginTop: "0.35rem",
          overflow: "hidden",
          position: "relative",
          width: "100%",
        }}
      >
        <div
          data-testid="source-credibility-fill"
          style={{
            background: credibility.confident ? fill : "rgba(255,255,255,0.18)",
            height: "100%",
            transition: "width 200ms ease",
            width: `${score}%`,
          }}
        />
      </div>
      <div
        style={{
          color: "var(--currents-parchment-dim)",
          display: "flex",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.7rem",
          justifyContent: "space-between",
          marginTop: "0.3rem",
        }}
      >
        <span data-testid="source-credibility-score">
          {credibility.confident
            ? `${score.toFixed(score % 1 === 0 ? 0 : 1)} / 100`
            : `n=${credibility.n_updates} updates`}
        </span>
        <span style={{ color: "var(--currents-muted)" }}>{summary}</span>
      </div>
      {!credibility.confident ? (
        <p
          style={{
            color: "var(--currents-muted)",
            fontSize: "0.72rem",
            lineHeight: 1.4,
            margin: "0.35rem 0 0",
          }}
        >
          {unconfidentCaveat(credibility)}
        </p>
      ) : null}
    </div>
  );
}

export default function CitationPopover({
  open,
  onClose,
  anchorRef,
  citation,
  conclusionText,
  publicUrl,
  id,
}: CitationPopoverProps) {
  const rawId = useId();
  const popoverId = id ?? `citation-popover-${rawId.replace(/:/g, "")}`;
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  const href = canExposePublicUrl(citation, publicUrl) ? safeHref(publicUrl) : null;
  const text =
    conclusionText.trim() ||
    citation.quoted_span.trim() ||
    "Firm conclusion text unavailable.";

  const updatePosition = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) {
      onClose();
      return;
    }
    if (anchorIsOutsideViewport(anchor)) {
      onClose();
      return;
    }
    setPosition(positionFor(anchor, dialogRef.current));
  }, [anchorRef, onClose]);

  useEffect(() => {
    if (!open) return;
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (dialogRef.current?.contains(target)) return;
      if (anchorRef.current?.contains(target)) return;
      onClose();
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [anchorRef, onClose, open]);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement;
    const frame = window.requestAnimationFrame(() => {
      const dialog = dialogRef.current;
      if (!dialog) return;
      const [first] = focusableElements(dialog);
      (first ?? dialog).focus();
    });

    return () => {
      window.cancelAnimationFrame(frame);
      if (isHTMLElement(previousFocus)) previousFocus.focus();
    };
  }, [open]);

  const trapFocus = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Tab") return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusable = focusableElements(dialog);
    if (!focusable.length) {
      event.preventDefault();
      dialog.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  if (!open || typeof document === "undefined") return null;

  const standing = normalizedStanding(citation);
  const standingMeta = standing === "active" ? null : STANDING_STYLE[standing];
  const reason = standingReason(citation);
  const credibility = normalizeCredibilityPayload(
    citation.source_credibility ?? citation.sourceCredibility ?? null,
  );
  const verdict = normalizeVerdictPayload(
    citation.citation_verdict ?? citation.citationVerdict ?? null,
  );

  return createPortal(
    <div
      aria-modal="false"
      id={popoverId}
      onKeyDown={trapFocus}
      ref={dialogRef}
      role="dialog"
      style={{
        ...shellStyle,
        left: `${position?.left ?? MARGIN}px`,
        opacity: position ? 1 : 0,
        top: `${position?.top ?? MARGIN}px`,
        width: `${position?.width ?? WIDTH}px`,
      }}
      tabIndex={-1}
    >
      <div
        style={{
          alignItems: "start",
          display: "flex",
          gap: "0.75rem",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div style={captionStyle}>{citationKind(citation)}</div>
          <h2 style={titleStyle}>{citationTitle(citation)}</h2>
          {standingMeta ? (
            <div style={{ marginTop: "0.4rem" }}>
              <span
                aria-label={`Source standing: ${standingMeta.label}`}
                data-testid="source-standing-pill"
                style={{
                  background: standingMeta.bg,
                  border: "1px solid rgba(0,0,0,0.35)",
                  borderRadius: "999px",
                  color: standingMeta.fg,
                  display: "inline-block",
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "0.65rem",
                  letterSpacing: "0.1em",
                  padding: "0.15rem 0.55rem",
                  textTransform: "uppercase",
                }}
              >
                {standingMeta.label}
              </span>
              {reason ? (
                <span
                  style={{
                    color: "var(--currents-muted)",
                    fontSize: "0.72rem",
                    marginLeft: "0.55rem",
                  }}
                >
                  {reason}
                </span>
              ) : null}
              {standing === "retracted" || standing === "corrected" ? (
                <a
                  href="/methodology#source-standing"
                  style={{
                    color: "var(--currents-gold)",
                    display: "inline-block",
                    fontSize: "0.72rem",
                    marginLeft: "0.55rem",
                    textDecoration: "underline",
                  }}
                >
                  this source has been retracted →
                </a>
              ) : null}
            </div>
          ) : null}
          {verdict ? <CitationVerdictPill verdict={verdict} /> : null}
        </div>
        <button
          aria-label="Close citation"
          onClick={onClose}
          style={{
            background: "transparent",
            border: "1px solid var(--currents-border)",
            borderRadius: "4px",
            color: "var(--currents-parchment-dim)",
            cursor: "pointer",
            fontSize: "0.8rem",
            lineHeight: 1,
            padding: "0.25rem 0.35rem",
          }}
          type="button"
        >
          ×
        </button>
      </div>

      {credibility ? (
        <CredibilityStrip credibility={credibility} />
      ) : null}

      <div style={bodyStyle}>{renderSafeMarkdown(text)}</div>

      {href ? (
        <a href={href} rel="noopener nofollow ugc" style={linkStyle} target="_blank">
          Open the public conclusion →
        </a>
      ) : (
        <p style={privateNoteStyle}>
          Source recorded by the firm; not publicly available.
        </p>
      )}
    </div>,
    document.body,
  );
}
