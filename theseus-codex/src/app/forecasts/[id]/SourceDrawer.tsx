"use client";

import type {
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent,
  ReactNode,
} from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import type {
  PublicForecast,
  PublicForecastSource,
} from "@/lib/forecastsTypes";

interface SourceDrawerProps {
  activeSourceId?: string | null;
  initiallyOpen?: boolean;
  onActiveSourceChange?: (sourceId: string, index: number) => void;
  sources: PublicForecastSource[];
}

interface ForecastEvidencePanelProps {
  prediction: PublicForecast;
  sources: PublicForecastSource[];
}

interface VerbatimContext {
  after: string;
  before: string;
  failedPreview: string;
  span: string;
  verified: boolean;
}

const CONTEXT_RADIUS = 200;
const PILL_ID_PREFIX = "forecast-citation-pill";
const DRAWER_ITEM_ID_PREFIX = "forecast-drawer-citation";

const drawerStyle: CSSProperties = {
  background: "var(--forecasts-bg-elevated)",
  border: "1px solid var(--forecasts-border)",
  borderRadius: "6px",
  padding: "0.95rem",
  position: "sticky",
  top: "1rem",
};

const eyebrowStyle: CSSProperties = {
  color: "var(--forecasts-muted)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.72rem",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const titleStyle: CSSProperties = {
  color: "var(--forecasts-parchment)",
  fontFamily: "'Cinzel', serif",
  fontSize: "0.92rem",
  letterSpacing: "0.08em",
  margin: "0 0 0.75rem",
  textTransform: "uppercase",
};

const pillStyle: CSSProperties = {
  background: "rgba(196, 160, 75, 0.13)",
  border: "1px solid var(--forecasts-cool-gold)",
  borderRadius: "999px",
  color: "var(--forecasts-cool-gold)",
  cursor: "pointer",
  display: "inline-flex",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.74rem",
  lineHeight: 1,
  margin: "0 0.12rem",
  padding: "0.2rem 0.35rem",
  verticalAlign: "baseline",
};

const markStyle: CSSProperties = {
  background: "var(--forecasts-cool-gold)",
  borderRadius: "3px",
  color: "#14130f",
  padding: "0.03rem 0.13rem",
};

function normalizedType(source: PublicForecastSource): string {
  const value = source.source_type.trim().toUpperCase();
  if (value === "CONCLUSION" || value === "CLAIM") return value;
  return value || "SOURCE";
}

function normalizedSupport(source: PublicForecastSource): string {
  const value = source.support_label.trim().toUpperCase();
  if (value === "DIRECT" || value === "INDIRECT" || value === "CONTRARY") {
    return value;
  }
  return value || "DIRECT";
}

function sourceKey(source: PublicForecastSource): string {
  return `${normalizedType(source)}/${source.source_id}`;
}

function pillId(sourceId: string): string {
  return `${PILL_ID_PREFIX}-${sourceId}`;
}

function drawerItemId(sourceId: string): string {
  return `${DRAWER_ITEM_ID_PREFIX}-${sourceId}`;
}

function supportStyle(label: string): CSSProperties {
  const color =
    label === "CONTRARY"
      ? "var(--forecasts-prob-no)"
      : label === "INDIRECT"
        ? "var(--forecasts-cool-gold)"
        : "var(--forecasts-prob-yes)";

  return {
    border: `1px solid ${color}`,
    borderRadius: "999px",
    color,
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: "0.66rem",
    fontWeight: 700,
    letterSpacing: "0.08em",
    padding: "0.24rem 0.42rem",
  };
}

function exactIndexOf(text: string, span: string): number {
  return span ? text.indexOf(span) : -1;
}

export function verbatimContext(
  sourceText: string,
  quotedSpan: string,
  radius = CONTEXT_RADIUS,
): VerbatimContext {
  const source = sourceText || "";
  const index = exactIndexOf(source, quotedSpan);

  if (index === -1) {
    const normalized = source.replace(/\s+/g, " ").trim();
    return {
      after: "",
      before: "",
      failedPreview:
        normalized.length > radius * 2
          ? `${normalized.slice(0, radius * 2)}...`
          : normalized,
      span: quotedSpan,
      verified: false,
    };
  }

  const start = Math.max(0, index - radius);
  const end = Math.min(source.length, index + quotedSpan.length + radius);

  return {
    after: source.slice(index + quotedSpan.length, end),
    before: source.slice(start, index),
    failedPreview: "",
    span: source.slice(index, index + quotedSpan.length),
    verified: true,
  };
}

export function nextCitationIndex(
  currentIndex: number,
  count: number,
  direction: 1 | -1,
): number {
  if (count <= 0) return -1;
  return (currentIndex + direction + count) % count;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (typeof HTMLElement === "undefined") return false;
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || target.isContentEditable;
}

function focusElement(id: string, scroll = false): void {
  if (typeof document === "undefined") return;
  const element = document.getElementById(id);
  if (!element) return;
  if (scroll) {
    element.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  element.focus({ preventScroll: !scroll });
}

function claimInlineText(source: PublicForecastSource): ReactNode {
  return (
    <span style={{ color: "var(--forecasts-parchment-dim)", fontSize: "0.84rem" }}>
      Claim text is rendered in-place because this public build does not expose a
      stable claim detail route.
    </span>
  );
}

function sourceLink(source: PublicForecastSource): ReactNode {
  if (normalizedType(source) !== "CONCLUSION") {
    return claimInlineText(source);
  }

  const href =
    source.canonical_path && source.canonical_path.startsWith("/c/")
      ? source.canonical_path
      : `/c/${encodeURIComponent(source.source_id)}`;

  return (
    <Link
      href={href}
      style={{
        color: "var(--forecasts-cool-gold)",
        fontSize: "0.86rem",
        textDecoration: "none",
      }}
    >
      View source
    </Link>
  );
}

function VerificationFailed({ context }: { context: VerbatimContext }) {
  return (
    <div
      role="alert"
      style={{
        border: "1px solid var(--forecasts-prob-no)",
        borderRadius: "6px",
        color: "var(--forecasts-parchment)",
        marginTop: "0.65rem",
        padding: "0.65rem",
      }}
    >
      <div
        style={{
          color: "var(--forecasts-prob-no)",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.72rem",
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        CITATION FAILED VERIFICATION
      </div>
      <p style={{ margin: "0.45rem 0 0", whiteSpace: "pre-wrap" }}>
        {context.span}
      </p>
      {context.failedPreview ? (
        <p
          style={{
            color: "var(--forecasts-muted)",
            fontSize: "0.82rem",
            lineHeight: 1.45,
            margin: "0.45rem 0 0",
          }}
        >
          Source preview: {context.failedPreview}
        </p>
      ) : null}
    </div>
  );
}

function HighlightedContext({ source }: { source: PublicForecastSource }) {
  const context = verbatimContext(source.source_text, source.quoted_span);

  if (!context.verified) {
    return <VerificationFailed context={context} />;
  }

  return (
    <p
      style={{
        color: "var(--forecasts-parchment)",
        fontSize: "0.92rem",
        lineHeight: 1.58,
        margin: "0.65rem 0 0",
        whiteSpace: "pre-wrap",
      }}
    >
      {context.before}
      <mark style={markStyle}>{context.span}</mark>
      {context.after}
    </p>
  );
}

export default function SourceDrawer({
  activeSourceId,
  initiallyOpen = true,
  onActiveSourceChange,
  sources,
}: SourceDrawerProps) {
  const [internalActiveSourceId, setInternalActiveSourceId] = useState<string | null>(null);
  const [internalOpen, setInternalOpen] = useState(initiallyOpen);

  const selectedSourceId = activeSourceId ?? internalActiveSourceId;
  const selectedIndex = sources.findIndex(
    (source) => source.source_id === selectedSourceId,
  );

  const selectIndex = useCallback(
    (index: number, options: { focusDrawer?: boolean; scroll?: boolean } = {}) => {
      if (!sources.length) return;
      const bounded = ((index % sources.length) + sources.length) % sources.length;
      const source = sources[bounded];
      setInternalOpen(true);
      setInternalActiveSourceId(source.source_id);
      onActiveSourceChange?.(source.source_id, bounded);

      if (options.focusDrawer && typeof window !== "undefined") {
        window.setTimeout(() => {
          focusElement(drawerItemId(source.source_id), options.scroll);
        }, 0);
      }
    },
    [onActiveSourceChange, sources],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) return;
      if (event.key === "Escape") {
        setInternalOpen(false);
        return;
      }
      if (event.key !== "[" && event.key !== "]") return;

      event.preventDefault();
      const direction = event.key === "]" ? 1 : -1;
      selectIndex(nextCitationIndex(selectedIndex, sources.length, direction), {
        focusDrawer: true,
        scroll: true,
      });
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectIndex, selectedIndex, sources.length]);

  const handleDrawerTab = (
    event: ReactKeyboardEvent<HTMLElement>,
    index: number,
  ) => {
    if (event.key !== "Tab" || sources.length === 0) return;
    event.preventDefault();
    const nextIndex = event.shiftKey
      ? index
      : nextCitationIndex(index, sources.length, 1);
    focusElement(pillId(sources[nextIndex].source_id));
  };

  if (!internalOpen) {
    return (
      <aside aria-label="Citation drawer" style={drawerStyle}>
        <button
          onClick={() => setInternalOpen(true)}
          style={{
            background: "transparent",
            border: "1px solid var(--forecasts-border)",
            borderRadius: "999px",
            color: "var(--forecasts-cool-gold)",
            cursor: "pointer",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.78rem",
            padding: "0.42rem 0.65rem",
          }}
          type="button"
        >
          Open citations
        </button>
      </aside>
    );
  }

  return (
    <aside aria-label="Citation drawer" id="forecast-citation-drawer" style={drawerStyle}>
      <div
        style={{
          alignItems: "center",
          display: "flex",
          gap: "0.75rem",
          justifyContent: "space-between",
        }}
      >
        <h2 style={titleStyle}>Citation drawer</h2>
        <button
          aria-label="Close citation drawer"
          onClick={() => setInternalOpen(false)}
          style={{
            background: "transparent",
            border: "1px solid var(--forecasts-border)",
            borderRadius: "999px",
            color: "var(--forecasts-muted)",
            cursor: "pointer",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.72rem",
            lineHeight: 1,
            padding: "0.34rem 0.45rem",
          }}
          type="button"
        >
          Esc
        </button>
      </div>

      <div style={{ display: "grid", gap: "0.8rem" }}>
        {sources.map((source, index) => {
          const active = source.source_id === selectedSourceId;
          const support = normalizedSupport(source);
          return (
            <article
              aria-current={active ? "true" : undefined}
              data-active={active ? "true" : "false"}
              id={drawerItemId(source.source_id)}
              key={`${source.id}-${source.source_id}`}
              onKeyDown={(event) => handleDrawerTab(event, index)}
              tabIndex={active ? 0 : -1}
              style={{
                background: active ? "rgba(196, 160, 75, 0.09)" : "transparent",
                border: active
                  ? "1px solid var(--forecasts-cool-gold)"
                  : "1px solid var(--forecasts-border)",
                borderRadius: "6px",
                outline: "none",
                padding: "0.8rem",
                scrollMarginTop: "1rem",
              }}
            >
              <div
                style={{
                  alignItems: "center",
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "0.45rem",
                  justifyContent: "space-between",
                }}
              >
                <span style={eyebrowStyle}>
                  [{index + 1}] {sourceKey(source)}
                </span>
                <span style={supportStyle(support)}>{support}</span>
              </div>

              <HighlightedContext source={source} />

              <div
                style={{
                  borderTop: "1px solid var(--forecasts-border)",
                  marginTop: "0.7rem",
                  paddingTop: "0.6rem",
                }}
              >
                {sourceLink(source)}
              </div>
            </article>
          );
        })}
      </div>
    </aside>
  );
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function paragraphize(markdown: string): string[] {
  return markdown
    .replace(/\r\n?/g, "\n")
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.replace(/[ \t]*\n[ \t]*/g, " ").trim())
    .filter(Boolean);
}

function citationPill(
  source: PublicForecastSource,
  index: number,
  activeSourceId: string | null,
  onSelect: (index: number) => void,
  options: { includeId?: boolean } = {},
): ReactNode {
  const active = source.source_id === activeSourceId;
  return (
    <button
      aria-controls="forecast-citation-drawer"
      aria-label={`Citation ${index + 1}: ${sourceKey(source)}`}
      id={options.includeId === false ? undefined : pillId(source.source_id)}
      key={`pill-${source.source_id}-${index}`}
      onClick={() => onSelect(index)}
      style={{
        ...pillStyle,
        background: active ? "var(--forecasts-cool-gold)" : pillStyle.background,
        color: active ? "#14130f" : pillStyle.color,
      }}
      type="button"
    >
      [{index + 1}]
    </button>
  );
}

function plainTextWithPills(
  paragraph: string,
  sources: PublicForecastSource[],
  activeSourceId: string | null,
  onSelect: (index: number) => void,
  options: { includeIds?: boolean } = {},
): { nodes: ReactNode[]; inserted: boolean } {
  const nodes: ReactNode[] = [];
  const numericMarker = /\[(\d+)\]/g;
  const hasNumericMarker = numericMarker.test(paragraph);
  numericMarker.lastIndex = 0;

  const sourceIds = sources
    .map((source) => source.source_id)
    .filter(Boolean)
    .sort((left, right) => right.length - left.length);
  const idPattern =
    !hasNumericMarker && sourceIds.length
      ? new RegExp(sourceIds.map(escapeRegExp).join("|"), "g")
      : null;
  const pattern = hasNumericMarker ? numericMarker : idPattern;

  if (!pattern) return { inserted: false, nodes: [paragraph] };

  let cursor = 0;
  let inserted = false;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(paragraph))) {
    if (match.index > cursor) {
      nodes.push(paragraph.slice(cursor, match.index));
    }

    if (hasNumericMarker) {
      const citationIndex = Number.parseInt(match[1], 10) - 1;
      const source = sources[citationIndex];
      if (source) {
        inserted = true;
        nodes.push(
          citationPill(source, citationIndex, activeSourceId, onSelect, {
            includeId: options.includeIds,
          }),
        );
      } else {
        nodes.push(match[0]);
      }
    } else {
      const sourceId = match[0];
      const citationIndex = sources.findIndex((source) => source.source_id === sourceId);
      nodes.push(sourceId);
      if (citationIndex >= 0) {
        inserted = true;
        nodes.push(
          citationPill(sources[citationIndex], citationIndex, activeSourceId, onSelect, {
            includeId: options.includeIds,
          }),
        );
      }
    }

    cursor = match.index + match[0].length;
  }

  if (cursor < paragraph.length) {
    nodes.push(paragraph.slice(cursor));
  }
  return { inserted, nodes };
}

function reasoningMarkdown(prediction: PublicForecast): string {
  const withAlias = prediction as PublicForecast & { reasoning_markdown?: string };
  return withAlias.reasoning_markdown ?? prediction.reasoning;
}

export function ForecastEvidencePanel({
  prediction,
  sources,
}: ForecastEvidencePanelProps) {
  const [activeSourceId, setActiveSourceId] = useState<string | null>(
    sources[0]?.source_id ?? null,
  );

  const paragraphs = useMemo(
    () => paragraphize(reasoningMarkdown(prediction)),
    [prediction],
  );
  const hasInlineCitationPills = useMemo(
    () =>
      paragraphs.some(
        (paragraph) =>
          /\[(\d+)\]/.test(paragraph) ||
          sources.some((source) => paragraph.includes(source.source_id)),
      ),
    [paragraphs, sources],
  );

  const selectCitation = useCallback(
    (index: number) => {
      const source = sources[index];
      if (!source) return;
      setActiveSourceId(source.source_id);
      if (typeof window !== "undefined") {
        window.setTimeout(() => {
          focusElement(drawerItemId(source.source_id), true);
        }, 0);
      }
    },
    [sources],
  );

  return (
    <section aria-label="Forecast reasoning and citations">
      <div
        style={{
          color: "var(--forecasts-parchment)",
          fontSize: "1.04rem",
          lineHeight: 1.7,
        }}
      >
        {paragraphs.map((paragraph, index) => (
          <p key={`reasoning-${index}`} style={index === 0 ? { marginTop: 0 } : undefined}>
            {
              plainTextWithPills(paragraph, sources, activeSourceId, selectCitation, {
                includeIds: hasInlineCitationPills,
              }).nodes
            }
          </p>
        ))}
      </div>

      {sources.length ? (
        <nav
          aria-label="Citation pills"
          style={{
            borderTop: "1px solid var(--forecasts-border)",
            display: "flex",
            flexWrap: "wrap",
            gap: "0.45rem",
            marginTop: "1rem",
            paddingTop: "0.8rem",
          }}
        >
          {sources.map((source, index) =>
            citationPill(source, index, activeSourceId, selectCitation, {
              includeId: !hasInlineCitationPills,
            }),
          )}
        </nav>
      ) : null}

      <div className="forecast-evidence-drawer">
        <SourceDrawer
          activeSourceId={activeSourceId}
          onActiveSourceChange={(sourceId) => setActiveSourceId(sourceId)}
          sources={sources}
        />
      </div>
    </section>
  );
}
