import type { CSSProperties } from "react";
import Link from "next/link";

import type { PublicOpinion } from "@/lib/currentsTypes";
import {
  DEFAULT_FILTER,
  filterToParams,
  opinionTopicId,
  type Filter,
} from "@/lib/filterMatch";

import OpinionCard from "./OpinionCard";

interface TopicClustersProps {
  opinions: PublicOpinion[];
  filter?: Filter;
}

interface TopicGroup {
  topic: string;
  opinions: PublicOpinion[];
}

const clustersStyle: CSSProperties = {
  display: "grid",
  gap: "0.8rem",
};

const detailsStyle: CSSProperties = {
  background: "rgba(232, 225, 211, 0.025)",
  border: "1px solid var(--currents-border)",
  borderRadius: "6px",
  overflow: "hidden",
};

const summaryStyle: CSSProperties = {
  alignItems: "center",
  color: "var(--currents-parchment)",
  cursor: "pointer",
  display: "flex",
  fontFamily: "'Cinzel', serif",
  fontSize: "0.86rem",
  gap: "0.6rem",
  justifyContent: "space-between",
  letterSpacing: "0.06em",
  padding: "0.8rem 0.9rem",
  textTransform: "uppercase",
};

const countStyle: CSSProperties = {
  color: "var(--currents-muted)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.72rem",
};

const bodyStyle: CSSProperties = {
  borderTop: "1px solid var(--currents-border)",
  display: "grid",
  gap: "0.75rem",
  padding: "0.8rem",
};

const moreLinkStyle: CSSProperties = {
  color: "var(--currents-gold)",
  fontFamily: "'IBM Plex Mono', monospace",
  fontSize: "0.78rem",
  justifySelf: "start",
  textDecoration: "none",
};

export function groupByTopic(opinions: PublicOpinion[]): TopicGroup[] {
  const groups = new Map<string, PublicOpinion[]>();

  for (const opinion of opinions) {
    const topic = opinionTopicId(opinion);
    const group = groups.get(topic);
    if (group) {
      group.push(opinion);
    } else {
      groups.set(topic, [opinion]);
    }
  }

  return Array.from(groups, ([topic, groupedOpinions]) => ({
    topic,
    opinions: groupedOpinions,
  })).sort((a, b) => {
    const countDelta = b.opinions.length - a.opinions.length;
    return countDelta || a.topic.localeCompare(b.topic);
  });
}

export function topicFeedHref(topic: string, filter: Filter = DEFAULT_FILTER): string {
  const params = filterToParams({ ...filter, topic, view: "feed" });
  const query = params.toString();
  return query ? `/currents?${query}` : "/currents";
}

export default function TopicClusters({
  opinions,
  filter = DEFAULT_FILTER,
}: TopicClustersProps) {
  const groups = groupByTopic(opinions);

  return (
    <div aria-label="Opinions grouped by topic" style={clustersStyle}>
      {groups.map((group) => {
        const shown = group.opinions.slice(0, 3);
        const hiddenCount = Math.max(0, group.opinions.length - shown.length);

        return (
          <details key={group.topic} open style={detailsStyle}>
            <summary style={summaryStyle}>
              <span>{group.topic}</span>
              <span style={countStyle}>{group.opinions.length}</span>
            </summary>
            <div style={bodyStyle}>
              {shown.map((opinion) => (
                <OpinionCard key={opinion.id} opinion={opinion} />
              ))}
              {hiddenCount ? (
                <Link href={topicFeedHref(group.topic, filter)} style={moreLinkStyle}>
                  +{hiddenCount} more
                </Link>
              ) : null}
            </div>
          </details>
        );
      })}
    </div>
  );
}
