"use client";

import type { MouseEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { PublicOpinion, PublicSource } from "@/lib/currentsTypes";
import { renderSafeMarkdown } from "@/lib/safeMarkdown";

import AuditTrail from "./AuditTrail";
import { CopyLinkButton } from "./CopyLinkButton";
import FollowupChat from "./FollowupChat";
import SourceCard from "./SourceCard";
import SourceDrawer from "./SourceDrawer";

interface DetailClientProps {
  opinion: PublicOpinion;
  sources: PublicSource[];
}

function sourceIdFromHash(hash: string): string | null {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!raw.startsWith("src-")) return null;

  const encodedId = raw.slice(4);
  try {
    return decodeURIComponent(encodedId);
  } catch {
    return encodedId;
  }
}

function sourceHash(sourceId: string): string {
  return `#src-${encodeURIComponent(sourceId)}`;
}

function topicFor(opinion: PublicOpinion): string {
  return opinion.topic_hint || opinion.event?.topic_hint || "untagged";
}

export default function DetailClient({ opinion, sources }: DetailClientProps) {
  const sourceIds = useMemo(
    () => new Set(sources.map((source) => source.source_id)),
    [sources],
  );
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const selectedSource = useMemo(
    () =>
      sources.find((source) => source.source_id === selectedSourceId) ?? null,
    [selectedSourceId, sources],
  );

  const flashSource = useCallback((sourceId: string) => {
    window.requestAnimationFrame(() => {
      const element = document.getElementById(`src-${sourceId}`);
      if (!element) return;

      element.scrollIntoView({ block: "start", behavior: "smooth" });
      element.classList.remove("currents-source-flash");
      void element.offsetWidth;
      element.classList.add("currents-source-flash");
      window.setTimeout(() => {
        element.classList.remove("currents-source-flash");
      }, 1300);
    });
  }, []);

  const activateSource = useCallback(
    (sourceId: string, options: { pushHash?: boolean; scroll?: boolean } = {}) => {
      if (!sourceIds.has(sourceId)) return;

      setSelectedSourceId(sourceId);
      if (options.pushHash) {
        window.history.pushState(null, "", sourceHash(sourceId));
      }
      if (options.scroll !== false) {
        flashSource(sourceId);
      }
    },
    [flashSource, sourceIds],
  );

  useEffect(() => {
    const syncHash = () => {
      const sourceId = sourceIdFromHash(window.location.hash);
      if (sourceId) activateSource(sourceId);
    };

    syncHash();
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, [activateSource]);

  const handleCitationClick = (
    event: MouseEvent<HTMLAnchorElement>,
    sourceId: string,
  ) => {
    event.preventDefault();
    activateSource(sourceId, { pushHash: true });
  };

  return (
    <>
      <div className="currents-detail-grid">
        <div className="currents-detail-audit">
          <AuditTrail
            opinion={opinion}
            sources={sources}
            onSourceSelect={(sourceId) => activateSource(sourceId, { pushHash: true })}
          />
        </div>

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
            <CopyLinkButton opinionId={opinion.id} />
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
          <div
            style={{
              color: "var(--currents-parchment)",
              fontSize: "1.05rem",
              lineHeight: 1.7,
            }}
          >
            {renderSafeMarkdown(opinion.body_markdown)}
          </div>

          {opinion.uncertainty_notes.length ? (
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
              {opinion.uncertainty_notes.map((note) => (
                <p key={note} style={{ margin: "0.25rem 0" }}>
                  {note}
                </p>
              ))}
            </section>
          ) : null}

          {sources.length ? (
            <nav
              aria-label="Citation links"
              style={{
                borderTop: "1px solid var(--currents-border)",
                display: "flex",
                flexWrap: "wrap",
                gap: "0.45rem",
                marginTop: "1.2rem",
                paddingTop: "0.85rem",
              }}
            >
              {sources.map((source, index) => (
                <a
                  key={source.id}
                  href={sourceHash(source.source_id)}
                  onClick={(event) => handleCitationClick(event, source.source_id)}
                  style={{
                    background:
                      selectedSourceId === source.source_id
                        ? "rgba(212, 160, 23, 0.13)"
                        : "transparent",
                    border:
                      selectedSourceId === source.source_id
                        ? "1px solid var(--currents-gold)"
                        : "1px solid var(--currents-border)",
                    borderRadius: "999px",
                    color: source.is_revoked
                      ? "var(--currents-amber)"
                      : "var(--currents-parchment-dim)",
                    fontSize: "0.78rem",
                    padding: "0.32rem 0.55rem",
                    textDecoration: "none",
                  }}
                >
                  {index + 1}. {source.source_kind.toLowerCase()}
                </a>
              ))}
            </nav>
          ) : null}

          <section
            aria-label="Expanded sources"
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
              Sources
            </h2>
            {sources.length ? (
              sources.map((source) => (
                <SourceCard
                  key={source.id}
                  source={source}
                  onSelect={(sourceId) =>
                    activateSource(sourceId, { pushHash: true })
                  }
                />
              ))
            ) : (
              <p style={{ color: "var(--currents-muted)", margin: 0 }}>
                No sources returned for this opinion.
              </p>
            )}
          </section>

          <FollowupChat opinionId={opinion.id} sources={sources} />
        </main>

        <div className="currents-detail-drawer">
          <SourceDrawer
            selectedSource={selectedSource}
            sources={sources}
            onSelect={(sourceId) => activateSource(sourceId, { pushHash: true })}
          />
        </div>
      </div>

      <style>{`
        .currents-detail-grid {
          display: grid;
          gap: 1rem;
          grid-template-columns: minmax(160px, 220px) minmax(0, 1fr) minmax(220px, 280px);
          align-items: start;
        }

        .currents-source-highlight {
          background: rgba(212, 160, 23, 0.25);
          color: var(--currents-parchment);
          padding: 0.03rem 0.12rem;
        }

        .currents-source-flash {
          animation: currents-source-flash 1.2s ease-out;
        }

        @keyframes currents-source-flash {
          0% {
            border-color: var(--currents-gold);
            box-shadow: 0 0 0 3px rgba(212, 160, 23, 0.32);
          }
          100% {
            box-shadow: 0 0 0 0 rgba(212, 160, 23, 0);
          }
        }

        @media (max-width: 980px) {
          .currents-detail-grid {
            grid-template-columns: minmax(0, 1fr);
          }

          .currents-detail-audit {
            order: 1;
          }

          .currents-detail-main {
            order: 2;
          }

          .currents-detail-drawer {
            order: 3;
          }

          .currents-detail-drawer aside {
            position: static !important;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .currents-source-flash {
            animation: none;
          }
        }
      `}</style>
    </>
  );
}
