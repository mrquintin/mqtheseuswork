"use client";

import {
  cloneElement,
  isValidElement,
  type CSSProperties,
  type ReactElement,
  type ReactNode,
  useCallback,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";

import type { PublicCitation, PublicOpinion } from "@/lib/currentsTypes";
import { relativeTime } from "@/lib/relativeTime";
import { renderSafeMarkdown } from "@/lib/safeMarkdown";
import CitationPopover from "@/components/CitationPopover";

import XPostEmbed from "./XPostEmbed";

type StanceKey = "agrees" | "disagrees" | "complicates" | "abstained";

const supportedStances = new Set<StanceKey>([
  "agrees",
  "disagrees",
  "complicates",
  "abstained",
]);

function stanceKey(rawStance: string): StanceKey {
  const normalized = rawStance.trim().toLowerCase();
  if (supportedStances.has(normalized as StanceKey)) return normalized as StanceKey;
  if (["agree", "support", "supports"].includes(normalized)) return "agrees";
  if (["disagree", "oppose", "opposes", "rejects", "refutes"].includes(normalized)) {
    return "disagrees";
  }
  if (["complicate", "mixed", "qualifies", "qualified"].includes(normalized)) {
    return "complicates";
  }
  if (["abstain", "abstains"].includes(normalized)) return "abstained";
  return "abstained";
}

function authorHandle(opinion: PublicOpinion): string | null {
  const handle = opinion.event?.author_handle?.trim();
  if (!handle) return null;
  return handle.startsWith("@") ? handle : `@${handle}`;
}

function sourceKind(rawSource: string | null | undefined): "x" | "rss" | "source" {
  const normalized = (rawSource || "").trim().toUpperCase();
  if (["X", "X_TWITTER", "TWITTER"].includes(normalized)) return "x";
  if (normalized === "RSS") return "rss";
  return "source";
}

function observedSourceTitle(opinion: PublicOpinion): string {
  switch (sourceKind(opinion.event?.source)) {
    case "x":
      return "X post";
    case "rss":
      return "RSS item";
    default:
      return "Observed item";
  }
}

function observedItemDisplayName(opinion: PublicOpinion): string {
  switch (sourceKind(opinion.event?.source)) {
    case "x":
      return "X post";
    case "rss":
      return "RSS item";
    default:
      return opinion.event?.source || "observed item";
  }
}

function observedItemLinkLabel(opinion: PublicOpinion): string {
  switch (sourceKind(opinion.event?.source)) {
    case "x":
      return "Open on X";
    case "rss":
      return "Open item";
    default:
      return "Open item";
  }
}

const cardStyle: CSSProperties = {
  background: "var(--currents-bg-elevated)",
  border: "1px solid var(--currents-border)",
  borderRadius: "6px",
  boxShadow: "0 12px 32px rgba(0, 0, 0, 0.18)",
  padding: "1rem 1rem 0.9rem",
};

const metaRowStyle: CSSProperties = {
  alignItems: "center",
  color: "var(--currents-muted)",
  display: "flex",
  flexWrap: "wrap",
  fontSize: "0.74rem",
  gap: "0.45rem",
  letterSpacing: "0.03em",
  marginBottom: "0.65rem",
};

const pillBaseStyle: CSSProperties = {
  borderRadius: "999px",
  fontSize: "0.68rem",
  fontWeight: 700,
  letterSpacing: "0.08em",
  lineHeight: 1,
  padding: "0.32rem 0.48rem",
  textTransform: "uppercase",
};

const headlineStyle: CSSProperties = {
  fontFamily: "'EB Garamond', serif",
  fontSize: "1.15rem",
  lineHeight: 1.25,
  margin: "0 0 0.55rem",
};

const bodyStyle: CSSProperties = {
  color: "var(--currents-parchment)",
  fontSize: "0.95rem",
  lineHeight: 1.6,
};

const observedSourceStyle: CSSProperties = {
  background: "rgba(232, 225, 211, 0.045)",
  border: "1px solid var(--currents-border)",
  borderRadius: "6px",
  marginBottom: "0.85rem",
  padding: "0.72rem 0.78rem",
};

const observedSourceMetaStyle: CSSProperties = {
  alignItems: "center",
  color: "var(--currents-muted)",
  display: "flex",
  flexWrap: "wrap",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.68rem",
  gap: "0.42rem",
  letterSpacing: "0.08em",
  marginBottom: "0.45rem",
  textTransform: "uppercase",
};

const observedSourceTextStyle: CSSProperties = {
  color: "var(--currents-parchment-dim)",
  display: "-webkit-box",
  fontSize: "0.86rem",
  lineHeight: 1.45,
  margin: 0,
  overflow: "hidden",
  WebkitBoxOrient: "vertical",
  WebkitLineClamp: 3,
};

const mutedStyle: CSSProperties = {
  color: "var(--currents-muted)",
  fontSize: "0.78rem",
};

type CitationMetadata = PublicCitation & {
  conclusion_text?: string | null;
  conclusionText?: string | null;
  conclusion_title?: string | null;
  conclusionTitle?: string | null;
  public_url?: string | null;
  publicUrl?: string | null;
  source_visibility?: string | null;
  visibility?: string | null;
};

interface OpinionCardProps {
  opinion: PublicOpinion;
  className?: string;
  detailBasePath?: string;
}

interface OpinionMarkdownBodyProps {
  opinion: PublicOpinion;
  className?: string;
  style?: CSSProperties;
}

const citationTokenStyle: CSSProperties = {
  background: "transparent",
  border: 0,
  color: "var(--currents-amber)",
  cursor: "pointer",
  font: "inherit",
  padding: 0,
  textDecoration: "underline",
  textDecorationStyle: "dotted",
};

function citationTokenText(citation: PublicCitation): string {
  const normalized = citation.source_kind.trim().toLowerCase();
  if (normalized === "claim") return "[opinion]";
  if (normalized === "conclusion") return "[firm conclusion]";
  return "[firm source]";
}

function citationConclusionText(citation: CitationMetadata): string {
  return (
    citation.conclusion_text?.trim() ||
    citation.conclusionText?.trim() ||
    citation.quoted_span.trim() ||
    "Firm conclusion text unavailable."
  );
}

function citationPublicUrl(citation: CitationMetadata): string | null {
  return citation.public_url ?? citation.publicUrl ?? null;
}

function replaceCitationMarkers(
  text: string,
  keyPrefix: string,
  citations: CitationMetadata[],
  popoverId: string,
  activeCitationId: string | null,
  onOpen: (citation: CitationMetadata, anchor: HTMLButtonElement) => void,
): ReactNode {
  const nodes: ReactNode[] = [];
  const markerPattern = /\[(?:(\d+)|C:([^\]\s]+))\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = markerPattern.exec(text)) !== null) {
    const citation = citationForMarker(citations, match[1], match[2]);
    if (!citation) continue;

    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    nodes.push(
      <button
        aria-controls={popoverId}
        aria-expanded={activeCitationId === citation.id}
        aria-haspopup="dialog"
        key={`${keyPrefix}-citation-${match.index}-${match[1]}`}
        onClick={(event) => onOpen(citation, event.currentTarget)}
        style={citationTokenStyle}
        type="button"
      >
        {citationTokenText(citation)}
      </button>,
    );
    lastIndex = markerPattern.lastIndex;
  }

  if (!nodes.length) return text;
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function citationForMarker(
  citations: CitationMetadata[],
  numericMarker: string | undefined,
  sourceIdMarker: string | undefined,
): CitationMetadata | undefined {
  if (numericMarker) {
    const citationIndex = Number.parseInt(numericMarker, 10) - 1;
    return citations[citationIndex];
  }

  if (!sourceIdMarker) return undefined;
  return citations.find(
    (citation) =>
      citation.source_id === sourceIdMarker ||
      citation.id === sourceIdMarker,
  );
}

function injectCitationTokens(
  node: ReactNode,
  citations: CitationMetadata[],
  popoverId: string,
  activeCitationId: string | null,
  onOpen: (citation: CitationMetadata, anchor: HTMLButtonElement) => void,
  keyPrefix = "opinion-body",
): ReactNode {
  if (typeof node === "string") {
    return replaceCitationMarkers(
      node,
      keyPrefix,
      citations,
      popoverId,
      activeCitationId,
      onOpen,
    );
  }

  if (Array.isArray(node)) {
    return node.map((child, index) =>
      injectCitationTokens(
        child,
        citations,
        popoverId,
        activeCitationId,
        onOpen,
        `${keyPrefix}-${index}`,
      ),
    );
  }

  if (isValidElement<{ children?: ReactNode }>(node)) {
    const element = node as ReactElement<{ children?: ReactNode }>;
    if (element.props.children === undefined) return element;
    return cloneElement(
      element,
      undefined,
      injectCitationTokens(
        element.props.children,
        citations,
        popoverId,
        activeCitationId,
        onOpen,
        `${keyPrefix}-${String(element.key ?? "element")}`,
      ),
    );
  }

  return node;
}

export function OpinionMarkdownBody({ opinion, className, style }: OpinionMarkdownBodyProps) {
  const rawPopoverId = useId();
  const popoverId = `opinion-citation-popover-${opinion.id}-${rawPopoverId.replace(
    /:/g,
    "",
  )}`;
  const anchorRef = useRef<HTMLElement | null>(null);
  const [activeCitation, setActiveCitation] = useState<CitationMetadata | null>(null);
  const citations = opinion.citations as CitationMetadata[];
  const openCitation = useCallback(
    (citation: CitationMetadata, anchor: HTMLButtonElement) => {
      anchorRef.current = anchor;
      setActiveCitation(citation);
    },
    [],
  );
  const closeCitation = useCallback(() => {
    setActiveCitation(null);
  }, []);
  const renderedMarkdown = useMemo(
    () => renderSafeMarkdown(opinion.body_markdown),
    [opinion.body_markdown],
  );
  const body = useMemo(
    () =>
      injectCitationTokens(
        renderedMarkdown,
        citations,
        popoverId,
        activeCitation?.id ?? null,
        openCitation,
      ),
    [activeCitation?.id, citations, openCitation, popoverId, renderedMarkdown],
  );

  return (
    <div className={className} style={style}>
      {body}
      {activeCitation ? (
        <CitationPopover
          anchorRef={anchorRef}
          citation={activeCitation}
          conclusionText={citationConclusionText(activeCitation)}
          id={popoverId}
          onClose={closeCitation}
          open
          publicUrl={citationPublicUrl(activeCitation)}
        />
      ) : null}
    </div>
  );
}

function ObservedSourceExcerpt({ opinion }: { opinion: PublicOpinion }) {
  const event = opinion.event;
  const text = event?.text?.trim();
  if (!event || !text) return null;

  const handle = authorHandle(opinion);
  if (sourceKind(event.source) === "x" && event.url) {
    return (
      <XPostEmbed
        authorHandle={handle}
        compact
        fallbackText={text}
        observedAt={event.observed_at}
        surface="card"
        url={event.url}
      />
    );
  }

  const title = observedSourceTitle(opinion);

  return (
    <section aria-label={title} style={observedSourceStyle}>
      <div style={observedSourceMetaStyle}>
        <span>{title}</span>
        {handle ? <span>{handle}</span> : null}
        <span>{relativeTime(event.observed_at)}</span>
      </div>
      <p style={observedSourceTextStyle}>"{text}"</p>
      {event.url ? (
        <a
          href={event.url}
          rel="noopener nofollow ugc"
          target="_blank"
          style={{
            color: "var(--currents-gold)",
            display: "inline-block",
            fontSize: "0.78rem",
            marginTop: "0.5rem",
            textDecoration: "none",
          }}
        >
          {observedItemLinkLabel(opinion)}
        </a>
      ) : null}
    </section>
  );
}

export default function OpinionCard({
  opinion,
  className,
  detailBasePath = "/currents",
}: OpinionCardProps) {
  const stance = stanceKey(opinion.stance);
  const stanceColor = `var(--currents-stance-${stance})`;
  const href = `${detailBasePath.replace(/\/+$/, "")}/${encodeURIComponent(opinion.id)}`;
  const topic = opinion.topic_hint || opinion.event?.topic_hint || "untagged";
  const handle = authorHandle(opinion);
  const observedItemName = observedItemDisplayName(opinion);

  return (
    <article
      className={className}
      style={{
        ...cardStyle,
        borderLeft: `4px solid ${stanceColor}`,
      }}
    >
      <div style={metaRowStyle}>
        <span
          style={{
            ...pillBaseStyle,
            border: `1px solid ${stanceColor}`,
            color: stanceColor,
          }}
        >
          {stance}
        </span>
        <span
          style={{ color: "var(--currents-parchment-dim)" }}
        >
          {topic}
        </span>
        <span>· {relativeTime(opinion.generated_at)}</span>
      </div>

      <ObservedSourceExcerpt opinion={opinion} />

      <h2 style={headlineStyle}>
        <Link
          href={href}
          style={{
            color: "var(--currents-parchment)",
            textDecoration: "none",
          }}
        >
          {opinion.headline}
        </Link>
      </h2>

      <OpinionMarkdownBody opinion={opinion} style={bodyStyle} />

      {opinion.uncertainty_notes.length ? (
        <div
          style={{
            color: "var(--currents-amber)",
            fontSize: "0.88rem",
            fontStyle: "italic",
            lineHeight: 1.5,
            marginTop: "0.7rem",
          }}
        >
          {opinion.uncertainty_notes.map((note) => (
            <p key={note} style={{ margin: "0.2rem 0" }}>
              {note}
            </p>
          ))}
        </div>
      ) : null}

      <div
        style={{
          alignItems: "center",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.65rem",
          justifyContent: "space-between",
          marginTop: "0.8rem",
        }}
      >
        <Link
          href={`${href}#ask`}
          style={{
            color: "var(--currents-gold)",
            fontSize: "0.86rem",
            textDecoration: "none",
          }}
        >
          Ask a follow-up →
        </Link>
        <span style={mutedStyle}>
          {handle ? `${handle} · ` : ""}
          {opinion.event?.url ? (
            <a
              href={opinion.event.url}
              rel="noopener nofollow ugc"
              target="_blank"
              style={{ color: "var(--currents-muted)" }}
            >
              {observedItemName}
            </a>
          ) : (
            observedItemName
          )}
        </span>
      </div>
    </article>
  );
}
