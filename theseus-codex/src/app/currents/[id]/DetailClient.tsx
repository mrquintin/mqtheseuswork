"use client";

import Link from "next/link";

import type { PublicOpinion, PublicSource } from "@/lib/currentsTypes";
import CurrentsReconciliation from "@/components/CurrentsReconciliation";

import { CopyLinkButton } from "./CopyLinkButton";
import FollowupChat from "./FollowupChat";
import SourceCard from "./SourceCard";
import { OpinionMarkdownBody } from "../OpinionCard";
import XPostEmbed from "../XPostEmbed";

const NO_COUNTER_UNCERTAINTY_TAG = "no_canonical_counter_claim_found";

interface DetailClientProps {
  opinion: PublicOpinion;
  sources: PublicSource[];
}

function topicFor(opinion: PublicOpinion): string {
  return opinion.topic_hint || opinion.event?.topic_hint || "untagged";
}

function eventSourceKind(event: PublicOpinion["event"]): "x" | "rss" | "source" {
  const normalized = (event?.source || "").trim().toUpperCase();
  if (["X", "X_TWITTER", "TWITTER"].includes(normalized)) return "x";
  if (normalized === "RSS") return "rss";
  return "source";
}

function eventAuthorHandle(event: PublicOpinion["event"]): string | null {
  const handle = event?.author_handle?.trim();
  if (!handle) return null;
  return handle.startsWith("@") ? handle : `@${handle}`;
}

function observedEventTitle(event: PublicOpinion["event"]): string {
  switch (eventSourceKind(event)) {
    case "x":
      return "X post";
    case "rss":
      return "RSS item";
    default:
      return "Observed item";
  }
}

function sourceActionLabel(event: PublicOpinion["event"]): string {
  return eventSourceKind(event) === "x" ? "Open on X" : "Open item";
}

function formatObservedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  })} UTC`;
}

function ObservedEventPanel({ opinion }: { opinion: PublicOpinion }) {
  const event = opinion.event;
  const text = event?.text?.trim();
  if (!event || !text) return null;

  const title = observedEventTitle(event);
  const handle = eventAuthorHandle(event);

  if (eventSourceKind(event) === "x" && event.url) {
    return (
      <XPostEmbed
        authorHandle={handle}
        fallbackText={text}
        observedAt={event.observed_at}
        surface="page"
        url={event.url}
      />
    );
  }

  return (
    <section
      aria-label={title}
      style={{
        background: "rgba(232, 225, 211, 0.045)",
        border: "1px solid var(--currents-border)",
        borderRadius: "6px",
        margin: "0.6rem 0 1.15rem",
        padding: "0.9rem 1rem",
      }}
    >
      <div
        style={{
          alignItems: "center",
          color: "var(--currents-muted)",
          display: "flex",
          flexWrap: "wrap",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.72rem",
          gap: "0.55rem",
          justifyContent: "space-between",
          letterSpacing: "0.08em",
          marginBottom: "0.65rem",
          textTransform: "uppercase",
        }}
      >
        <span>{title}</span>
        <span
          style={{
            alignItems: "center",
            display: "inline-flex",
            flexWrap: "wrap",
            gap: "0.45rem",
          }}
        >
          {handle ? <span>{handle}</span> : null}
          <span>{formatObservedAt(event.observed_at)}</span>
        </span>
      </div>
      <blockquote
        style={{
          borderLeft: "3px solid var(--currents-gold)",
          color: "var(--currents-parchment)",
          fontSize: "1rem",
          lineHeight: 1.6,
          margin: 0,
          paddingLeft: "0.85rem",
          whiteSpace: "pre-wrap",
        }}
      >
        {text}
      </blockquote>
      <div
        style={{
          alignItems: "center",
          color: "var(--currents-muted)",
          display: "flex",
          flexWrap: "wrap",
          fontSize: "0.82rem",
          gap: "0.65rem",
          marginTop: "0.75rem",
        }}
      >
        {event.url ? (
          <a
            href={event.url}
            rel="noopener nofollow ugc"
            target="_blank"
            style={{ color: "var(--currents-gold)", textDecoration: "none" }}
          >
            {sourceActionLabel(event)}
          </a>
        ) : null}
      </div>
    </section>
  );
}

export default function DetailClient({ opinion, sources }: DetailClientProps) {
  return (
    <>
      <Link
        aria-label="Back to Currents"
        href="/currents"
        style={{
          color: "var(--currents-gold)",
          display: "inline-flex",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: "0.75rem",
          letterSpacing: "0.08em",
          marginBottom: "1rem",
          textDecoration: "none",
          textTransform: "uppercase",
        }}
      >
        ← Currents
      </Link>

      <div className="currents-detail-grid">
        <main className="currents-detail-main">
          <div
            style={{
              alignItems: "center",
              color: "var(--currents-muted)",
              display: "flex",
              flexWrap: "wrap",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.75rem",
              gap: "0.6rem",
              justifyContent: "space-between",
              letterSpacing: "0.08em",
              marginBottom: "0.6rem",
              textTransform: "uppercase",
            }}
          >
            <span>
              {opinion.stance} · {topicFor(opinion)}
            </span>
            <span style={{ alignItems: "center", display: "inline-flex", flexWrap: "wrap", gap: "0.5rem" }}>
              <CopyLinkButton opinionId={opinion.id} />
            </span>
          </div>
          <h1
            style={{
              color: "var(--currents-parchment)",
              fontFamily: "'EB Garamond', serif",
              fontSize: "clamp(2rem, 4vw, 3.2rem)",
              lineHeight: 1.05,
              margin: "0 0 1rem",
            }}
          >
            {opinion.headline}
          </h1>

          <ObservedEventPanel opinion={opinion} />

          <div
            style={{
              color: "var(--currents-muted)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.74rem",
              letterSpacing: "0.08em",
              marginBottom: "0.45rem",
              textTransform: "uppercase",
            }}
          >
            The firm's opinion
          </div>
          <OpinionMarkdownBody
            opinion={opinion}
            style={{
              color: "var(--currents-parchment)",
              fontSize: "1.05rem",
              lineHeight: 1.7,
            }}
          />

          <CurrentsReconciliation reconciliation={opinion.reconciliation ?? null} />

          {(() => {
            const visibleNotes = opinion.uncertainty_notes.filter(
              (note) => note !== NO_COUNTER_UNCERTAINTY_TAG,
            );
            return visibleNotes.length ? (
              <section
                aria-label="Uncertainty notes"
                style={{
                  borderLeft: "3px solid var(--currents-amber)",
                  color: "var(--currents-amber)",
                  fontSize: "0.94rem",
                  fontStyle: "italic",
                  lineHeight: 1.55,
                  marginTop: "1rem",
                  paddingLeft: "0.85rem",
                }}
              >
                {visibleNotes.map((note) => (
                  <p key={note} style={{ margin: "0.25rem 0" }}>
                    {note}
                  </p>
                ))}
              </section>
            ) : null;
          })()}

          <section
            aria-label="Firm sources"
            style={{
              display: "grid",
              gap: "0.9rem",
              marginTop: "1.75rem",
            }}
          >
            <h2
              style={{
                color: "var(--currents-parchment)",
                fontFamily: "'Cinzel', serif",
                fontSize: "1rem",
                letterSpacing: "0.08em",
                margin: 0,
                textTransform: "uppercase",
              }}
            >
              Firm sources
            </h2>
            {sources.length ? (
              sources.map((source) => (
                <SourceCard key={source.id} source={source} />
              ))
            ) : (
              <p style={{ color: "var(--currents-muted)", margin: 0 }}>
                No firm sources returned for this opinion.
              </p>
            )}
          </section>

          <FollowupChat opinionId={opinion.id} sources={sources} />
        </main>
      </div>

      <style>{`
        .currents-detail-grid {
          display: grid;
          gap: 1rem;
          grid-template-columns: minmax(0, 1fr);
          align-items: start;
        }

        .currents-source-highlight {
          background: rgba(212, 160, 23, 0.25);
          color: var(--currents-parchment);
          padding: 0.03rem 0.12rem;
        }

        @media (max-width: 980px) {
          .currents-detail-grid {
            grid-template-columns: minmax(0, 1fr);
          }

          .currents-detail-main {
            order: 1;
          }
        }
      `}</style>
    </>
  );
}
