"use client";

import { useMemo, useState } from "react";
import { GitBranch, Lock, Network, Table2 } from "lucide-react";

import type {
  CatalystKind,
  ConversationGeometry,
  YearEndConversationStats,
} from "@/lib/conversationGeometry";

type View = "map" | "weighting" | "catalysts";

type Props = {
  geometry: ConversationGeometry;
  uploadId: string;
  yearStats: YearEndConversationStats;
};

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function scoreLabel(score: number): string {
  return score.toFixed(1).replace(/\.0$/, "");
}

const CATALYST_LABELS: Record<CatalystKind, string> = {
  "question-response": "Question handoff",
  agreement: "Agreement",
  disagreement: "Disagreement",
  "causal-continuation": "Causal language",
  "conceptual-carry": "Conceptual carry",
  "neutral-handoff": "Neutral handoff",
};

export default function ConversationGeometryPanel({
  geometry,
  uploadId,
  yearStats,
}: Props) {
  const [view, setView] = useState<View>("map");
  const nodePositions = useMemo(() => {
    const count = Math.max(geometry.speakers.length, 1);
    return new Map(
      geometry.speakers.map((speaker, index) => {
        const angle = -Math.PI / 2 + (2 * Math.PI * index) / count;
        return [
          speaker.id,
          {
            x: 50 + Math.cos(angle) * 34,
            y: 50 + Math.sin(angle) * 30,
          },
        ];
      }),
    );
  }, [geometry.speakers]);

  const maxEdgeWeight = Math.max(1, ...geometry.edges.map((edge) => edge.weight));
  const topCatalysts = useMemo(
    () =>
      [...geometry.catalysts]
        .filter((item) => item.source !== item.target)
        .sort(
          (a, b) =>
            b.score - a.score ||
            a.sourceLabel.localeCompare(b.sourceLabel) ||
            a.targetLabel.localeCompare(b.targetLabel) ||
            a.toChunkId.localeCompare(b.toChunkId),
        )
        .slice(0, 8),
    [geometry.catalysts],
  );

  return (
    <section
      aria-labelledby="conversation-geometry-title"
      className="portal-card conversation-geometry"
    >
      <div className="conversation-geometry-header">
        <div>
          <p className="mono conversation-geometry-kicker">Conversation geometry</p>
          <h2 id="conversation-geometry-title">Harvest table</h2>
          <p>
            {geometry.speakers.length} voices / {geometry.totalHandoffs} handoffs /{" "}
            {geometry.totalWords} words
          </p>
        </div>
        <div className="conversation-geometry-tabs" role="tablist" aria-label="Conversation geometry views">
          <button
            aria-pressed={view === "map"}
            className="conversation-tab"
            onClick={() => setView("map")}
            type="button"
          >
            <Network aria-hidden="true" size={15} />
            Map
          </button>
          <button
            aria-pressed={view === "weighting"}
            className="conversation-tab"
            onClick={() => setView("weighting")}
            type="button"
          >
            <Table2 aria-hidden="true" size={15} />
            Weighting
          </button>
          <button
            aria-pressed={view === "catalysts"}
            className="conversation-tab"
            onClick={() => setView("catalysts")}
            type="button"
          >
            <GitBranch aria-hidden="true" size={15} />
            Catalysts
          </button>
        </div>
      </div>

      {!geometry.hasSpeakerLabels ? (
        <p className="conversation-geometry-note">
          No speaker labels were found, so the map treats this transcript as unattributed.
        </p>
      ) : null}

      <div className="conversation-map-grid" hidden={view !== "map"}>
        <div className="conversation-map-frame" aria-label="Speaker handoff map">
          <svg className="conversation-map" role="img" viewBox="0 0 100 100">
            <title>Speaker objects connected by weighted handoff lines</title>
            {geometry.edges.map((edge) => {
              const source = nodePositions.get(edge.source);
              const target = nodePositions.get(edge.target);
              if (!source || !target) return null;
              return (
                <line
                  className="conversation-edge"
                  key={edge.id}
                  strokeWidth={1.1 + (edge.weight / maxEdgeWeight) * 4.2}
                  x1={source.x}
                  x2={target.x}
                  y1={source.y}
                  y2={target.y}
                />
              );
            })}
            {geometry.speakers.map((speaker) => {
              const position = nodePositions.get(speaker.id) ?? { x: 50, y: 50 };
              return (
                <a href={`#chunk-${speaker.firstChunkId}`} key={speaker.id}>
                  <circle className="conversation-node" cx={position.x} cy={position.y} r="6.8" />
                  <text className="conversation-node-label" x={position.x} y={position.y + 12}>
                    {speaker.label}
                  </text>
                </a>
              );
            })}
          </svg>
        </div>
        <YearEndCard yearStats={yearStats} />
      </div>

      <div
        className="conversation-weighting"
        hidden={view !== "weighting"}
        role="table"
        aria-label="Speaker weighting"
      >
        {geometry.speakers.map((speaker) => (
          <div className="conversation-speaker-row" key={speaker.id} role="row">
            <div role="cell">
              <a className="conversation-speaker-name" href={`#chunk-${speaker.firstChunkId}`}>
                {speaker.label}
              </a>
              <span className="mono">
                {speaker.turns} turns / {speaker.questionTurns} questions /{" "}
                {Math.round(speaker.averageTurnWords)} words per turn
              </span>
            </div>
            <div className="conversation-share" role="cell">
              <span className="mono">{percent(speaker.share)}</span>
              <div aria-hidden="true" className="conversation-share-bar">
                <span style={{ width: percent(speaker.share) }} />
              </div>
            </div>
            <div className="conversation-term-row" role="cell">
              {speaker.terms.length
                ? speaker.terms.map((term) => (
                    <span className="conversation-term" key={term}>
                      {term}
                    </span>
                  ))
                : "No repeated terms"}
            </div>
          </div>
        ))}
      </div>

      <div hidden={view !== "catalysts"}>
        <p className="conversation-geometry-note">
          Catalyst scores rank adjacent speaker handoffs by visible transcript cues,
          not definitive causality or hidden motive.
        </p>

        {topCatalysts.length > 0 ? (
          <ol className="conversation-catalyst-list">
            {topCatalysts.map((item) => (
              <li className="conversation-catalyst" key={item.id}>
                <div>
                  <span className="mono conversation-catalyst-kind">
                    {CATALYST_LABELS[item.kind]} / score {scoreLabel(item.score)}
                  </span>
                  <a href={`/transcripts/${encodeURIComponent(uploadId)}?anchor=${encodeURIComponent(item.anchor)}`}>
                    {item.sourceLabel}{" -> "}{item.targetLabel}
                  </a>
                </div>
                <p>
                  <span className="mono">Source / {item.sourceLabel}</span>{" "}
                  <strong>{item.fromExcerpt}</strong>
                </p>
                <p>
                  <span className="mono">Target / {item.targetLabel}</span>{" "}
                  {item.toExcerpt}
                </p>
                <div className="conversation-term-row" aria-label="Shared terms">
                  {item.sharedTerms.length ? (
                    item.sharedTerms.map((term) => (
                      <span className="conversation-term" key={term}>
                        {term}
                      </span>
                    ))
                  ) : (
                    <span className="conversation-term">No shared terms</span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="conversation-geometry-note">
            No cross-speaker catalyst handoffs were detected in this transcript.
          </p>
        )}
      </div>
    </section>
  );
}

function YearEndCard({ yearStats }: { yearStats: YearEndConversationStats }) {
  if (yearStats.status !== "ready") {
    return (
      <aside className="conversation-year-card conversation-year-card-locked">
        <Lock aria-hidden="true" size={16} />
        <span className="mono">Year-end signal locked</span>
        <p>
          {yearStats.year} aggregates publish after the season closes, so the
          statistic cannot steer live conversations while the year is still open.
        </p>
      </aside>
    );
  }

  return (
    <aside className="conversation-year-card">
      <span className="mono">{yearStats.year} season signal</span>
      <dl>
        <div>
          <dt>Center of gravity</dt>
          <dd>
            {yearStats.topSpeakerLabel ?? "Unknown"}{" "}
            <span>{percent(yearStats.topSpeakerShare)}</span>
          </dd>
        </div>
        <div>
          <dt>Strongest bridge</dt>
          <dd>{yearStats.topBridgeLabel ?? "No cross-speaker bridge"}</dd>
        </div>
        <div>
          <dt>Transcripts</dt>
          <dd>{yearStats.transcriptCount}</dd>
        </div>
        <div>
          <dt>Total turns</dt>
          <dd>{yearStats.totalTurns}</dd>
        </div>
        <div>
          <dt>Total handoffs</dt>
          <dd>{yearStats.totalHandoffs}</dd>
        </div>
        <div>
          <dt>Participants</dt>
          <dd>{yearStats.participantCount}</dd>
        </div>
      </dl>
    </aside>
  );
}
