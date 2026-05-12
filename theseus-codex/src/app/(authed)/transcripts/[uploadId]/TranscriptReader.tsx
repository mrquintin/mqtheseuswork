"use client";

import { useMemo, useState } from "react";

export type TranscriptReaderChunk = {
  id: string;
  index: number;
  text: string;
  startMs: number | null;
  endMs: number | null;
  speakerLabel: string | null;
  headingHint: string | null;
};

type Props = {
  uploadId: string;
  chunks: TranscriptReaderChunk[];
};

function formatTimestamp(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function highlight(text: string, query: string) {
  const trimmed = query.trim();
  if (!trimmed) return text;
  const pattern = trimmed.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regex = new RegExp(`(${pattern})`, "ig");
  const parts = text.split(regex);
  return parts.map((part, idx) =>
    regex.test(part) ? (
      <mark className="transcript-search-hit" key={`${idx}-${part}`}>
        {part}
      </mark>
    ) : (
      <span key={`${idx}-${part}`}>{part}</span>
    ),
  );
}

export default function TranscriptReader({ uploadId, chunks }: Props) {
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState<string | null>(null);

  const trimmed = query.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!trimmed) return chunks;
    return chunks.filter((chunk) => {
      const haystack = `${chunk.text} ${chunk.speakerLabel ?? ""} ${chunk.headingHint ?? ""}`.toLowerCase();
      return haystack.includes(trimmed);
    });
  }, [trimmed, chunks]);

  const handleCopy = async (chunkId: string) => {
    const url =
      typeof window === "undefined"
        ? `/transcripts/${uploadId}?anchor=chunk-${chunkId}`
        : `${window.location.origin}/transcripts/${uploadId}?anchor=chunk-${chunkId}`;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
      }
      setCopied(chunkId);
      window.setTimeout(() => setCopied((current) => (current === chunkId ? null : current)), 1600);
    } catch {
      setCopied(null);
    }
  };

  return (
    <>
      <div className="transcript-reader-toolbar">
        <label className="transcript-reader-search">
          <span className="mono">Search transcript</span>
          <input
            aria-label="Search transcript"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter by word or phrase"
            type="search"
            value={query}
          />
        </label>
        <span className="mono transcript-reader-count">
          {trimmed ? `${filtered.length} of ${chunks.length} chunks` : `${chunks.length} chunks`}
        </span>
      </div>

      {filtered.length === 0 ? (
        <p className="transcript-reader-empty">No transcript chunks match {`"${query}"`}.</p>
      ) : (
        filtered.map((chunk) => {
          const anchor = `chunk-${chunk.id}`;
          return (
            <section
              className="transcript-chunk"
              data-testid={`transcript-chunk-${chunk.id}`}
              id={anchor}
              key={chunk.id}
            >
              <div className="transcript-chunk-grid">
                <div className="transcript-time-slot">
                  {chunk.startMs !== null ? (
                    <a
                      className="mono transcript-time"
                      href={`/transcripts/${encodeURIComponent(uploadId)}?anchor=${encodeURIComponent(anchor)}`}
                    >
                      [{formatTimestamp(chunk.startMs)}]
                    </a>
                  ) : (
                    <span className="mono transcript-chunk-index">[{chunk.index + 1}]</span>
                  )}
                  <button
                    aria-label={`Copy link to chunk ${chunk.index + 1}`}
                    className="mono transcript-chunk-copy"
                    onClick={() => handleCopy(chunk.id)}
                    type="button"
                  >
                    {copied === chunk.id ? "copied" : "copy link"}
                  </button>
                </div>
                <p className="transcript-body">
                  {chunk.speakerLabel ? (
                    <strong className="transcript-speaker">{chunk.speakerLabel}: </strong>
                  ) : null}
                  {highlight(chunk.text, query)}
                </p>
              </div>
            </section>
          );
        })
      )}
    </>
  );
}
