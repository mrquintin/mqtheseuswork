"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

export interface CapturePrinciple {
  id: string;
  text: string;
  confidenceTier: string;
  principleKind: string | null;
  sourceSpan: string | null;
  domainOfApplicability: string | null;
}

export interface CaptureRow {
  id: string;
  title: string;
  createdAtIso: string;
  status: string;
  audioUrl: string | null;
  audioDurationSec: number | null;
  transcript: string | null;
  extractionMethod: string | null;
  errorMessage: string | null;
  principles: CapturePrinciple[];
}

interface TriageState {
  /** "accepted-as-is" | "accepted-edited" | "rejected" | undefined (pending) */
  [principleId: string]: "accepted-as-is" | "accepted-edited" | "rejected" | undefined;
}

export default function CapturesClient({ rows }: { rows: CaptureRow[] }) {
  const router = useRouter();
  const [triageByCapture, setTriageByCapture] = useState<
    Record<string, TriageState>
  >({});

  function setTriage(
    captureId: string,
    principleId: string,
    decision: TriageState[string],
  ) {
    setTriageByCapture((prev) => ({
      ...prev,
      [captureId]: { ...(prev[captureId] ?? {}), [principleId]: decision },
    }));
  }

  async function handleDiscard(captureId: string) {
    const ok = window.confirm(
      "Discard this whole capture? The audio, transcript, and any extracted principles will be soft-deleted. This cannot be undone from the UI.",
    );
    if (!ok) return;
    const res = await fetch(`/api/upload/${captureId}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "Quick-capture discarded from /captures." }),
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      window.alert(`Discard failed: ${txt || res.status}`);
      return;
    }
    router.refresh();
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {rows.map((row) => (
        <CaptureCard
          key={row.id}
          row={row}
          triage={triageByCapture[row.id] ?? {}}
          onTriage={(pid, d) => setTriage(row.id, pid, d)}
          onDiscard={() => handleDiscard(row.id)}
        />
      ))}
    </div>
  );
}

function CaptureCard({
  row,
  triage,
  onTriage,
  onDiscard,
}: {
  row: CaptureRow;
  triage: TriageState;
  onTriage: (principleId: string, decision: TriageState[string]) => void;
  onDiscard: () => void;
}) {
  const recordedAt = useMemo(() => new Date(row.createdAtIso), [row.createdAtIso]);
  const duration = row.audioDurationSec
    ? formatDuration(row.audioDurationSec)
    : null;
  const inProgress =
    row.status === "pending" ||
    row.status === "extracting" ||
    row.status === "processing" ||
    row.status === "awaiting_ingest";
  return (
    <article
      style={{
        border: "1px solid rgba(0,0,0,0.1)",
        borderRadius: 12,
        padding: "1.1rem 1.25rem 1.25rem",
        background: "#fff",
        boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "0.75rem",
          marginBottom: "0.5rem",
        }}
      >
        <div>
          <h2
            style={{
              margin: 0,
              fontSize: "1rem",
              fontWeight: 600,
              letterSpacing: "0.01em",
            }}
          >
            {row.title}
          </h2>
          <p
            style={{
              margin: "0.15rem 0 0",
              fontSize: "0.78rem",
              color: "rgba(0,0,0,0.55)",
            }}
          >
            Recorded {recordedAt.toLocaleString()}
            {duration ? ` · ${duration}` : null}
            {row.extractionMethod ? ` · ${row.extractionMethod}` : null}
            <span
              style={{
                marginLeft: "0.5rem",
                padding: "0.05rem 0.45rem",
                borderRadius: 999,
                background: inProgress ? "#fef3c7" : "#ecfdf5",
                color: inProgress ? "#92400e" : "#065f46",
                fontSize: "0.7rem",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              {row.status}
            </span>
          </p>
        </div>
        <button
          type="button"
          onClick={onDiscard}
          style={{
            padding: "0.35rem 0.7rem",
            borderRadius: 6,
            border: "1px solid rgba(155,28,28,0.35)",
            background: "#fff",
            color: "#9b1c1c",
            fontSize: "0.78rem",
            cursor: "pointer",
          }}
        >
          Discard capture
        </button>
      </header>

      {row.audioUrl ? (
        <audio
          controls
          preload="none"
          src={row.audioUrl}
          style={{
            width: "100%",
            marginBottom: "0.6rem",
            height: 32,
          }}
        />
      ) : (
        <p
          style={{
            margin: "0 0 0.6rem",
            fontSize: "0.8rem",
            color: "rgba(0,0,0,0.55)",
            fontStyle: "italic",
          }}
        >
          Audio still uploading…
        </p>
      )}

      {row.errorMessage ? (
        <p
          role="alert"
          style={{
            margin: "0 0 0.6rem",
            fontSize: "0.8rem",
            color: "#9b1c1c",
          }}
        >
          {row.errorMessage}
        </p>
      ) : null}

      <section
        style={{
          background: "#fafaf7",
          border: "1px solid rgba(0,0,0,0.06)",
          borderRadius: 8,
          padding: "0.75rem 0.85rem",
          marginBottom: "0.85rem",
        }}
      >
        <h3
          style={{
            margin: "0 0 0.4rem",
            fontSize: "0.78rem",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "rgba(0,0,0,0.5)",
          }}
        >
          Transcript
        </h3>
        {row.transcript ? (
          <TranscriptWithHighlights
            transcript={row.transcript}
            principles={row.principles}
          />
        ) : (
          <p
            style={{
              margin: 0,
              fontStyle: "italic",
              color: "rgba(0,0,0,0.55)",
              fontSize: "0.85rem",
            }}
          >
            {inProgress
              ? "Transcribing… check back in a minute."
              : "No transcript available."}
          </p>
        )}
      </section>

      <section>
        <h3
          style={{
            margin: "0 0 0.5rem",
            fontSize: "0.78rem",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "rgba(0,0,0,0.5)",
          }}
        >
          Proposed principles ({row.principles.length})
        </h3>
        {row.principles.length === 0 ? (
          <p
            style={{
              margin: 0,
              fontStyle: "italic",
              color: "rgba(0,0,0,0.55)",
              fontSize: "0.85rem",
            }}
          >
            {inProgress
              ? "Extraction pending."
              : "No principles extracted from this capture."}
          </p>
        ) : (
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.65rem",
            }}
          >
            {row.principles.map((p) => (
              <PrincipleRow
                key={p.id}
                principle={p}
                decision={triage[p.id]}
                onTriage={(d) => onTriage(p.id, d)}
              />
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}

function PrincipleRow({
  principle,
  decision,
  onTriage,
}: {
  principle: CapturePrinciple;
  decision: TriageState[string];
  onTriage: (d: TriageState[string]) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(principle.text);
  const decided = Boolean(decision);
  return (
    <li
      style={{
        border: "1px solid rgba(0,0,0,0.08)",
        borderRadius: 8,
        padding: "0.65rem 0.8rem",
        background: decided ? "#f7f7f3" : "#fff",
        opacity: decision === "rejected" ? 0.6 : 1,
      }}
    >
      {principle.principleKind ? (
        <span
          style={{
            display: "inline-block",
            fontSize: "0.7rem",
            background: "#eef2ff",
            color: "#3730a3",
            padding: "0.05rem 0.4rem",
            borderRadius: 4,
            letterSpacing: "0.04em",
            marginBottom: "0.25rem",
          }}
        >
          {principle.principleKind}
        </span>
      ) : null}
      {editing ? (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          style={{
            width: "100%",
            fontSize: "0.9rem",
            lineHeight: 1.45,
            padding: "0.4rem 0.55rem",
            borderRadius: 6,
            border: "1px solid rgba(0,0,0,0.18)",
            fontFamily: "inherit",
          }}
        />
      ) : (
        <p style={{ margin: "0.1rem 0 0.4rem", fontSize: "0.92rem" }}>
          {draft}
        </p>
      )}
      {principle.domainOfApplicability ? (
        <p
          style={{
            margin: "0 0 0.4rem",
            fontSize: "0.78rem",
            color: "rgba(0,0,0,0.55)",
          }}
        >
          <em>Domain:</em> {principle.domainOfApplicability}
        </p>
      ) : null}
      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={() => {
            if (editing) {
              setEditing(false);
              onTriage("accepted-edited");
            } else {
              onTriage("accepted-as-is");
            }
          }}
          disabled={decision === "accepted-as-is" || decision === "accepted-edited"}
          style={triageBtn(
            "#0e7c3a",
            decision === "accepted-as-is" || decision === "accepted-edited",
          )}
        >
          {editing ? "Save & accept" : "Accept as is"}
        </button>
        <button
          type="button"
          onClick={() => setEditing((v) => !v)}
          disabled={Boolean(decision)}
          style={triageBtn("#1d4ed8", Boolean(decision))}
        >
          {editing ? "Cancel edit" : "Edit then accept"}
        </button>
        <button
          type="button"
          onClick={() => onTriage("rejected")}
          disabled={decision === "rejected"}
          style={triageBtn("#9b1c1c", decision === "rejected")}
        >
          Reject
        </button>
        {decision ? (
          <span
            style={{
              fontSize: "0.78rem",
              color: "rgba(0,0,0,0.55)",
              alignSelf: "center",
            }}
          >
            ({decision.replace("-", " ")})
          </span>
        ) : null}
      </div>
    </li>
  );
}

function TranscriptWithHighlights({
  transcript,
  principles,
}: {
  transcript: string;
  principles: CapturePrinciple[];
}) {
  // Highlight each principle's source span inline so the founder can
  // see WHERE in the memo the candidate came from. We render the
  // transcript verbatim, with spans matching a `sourceSpan` wrapped
  // in a tinted background.
  const spans = principles
    .map((p) => p.sourceSpan)
    .filter((s): s is string => Boolean(s && s.length > 6));
  let body: React.ReactNode = transcript;
  for (const span of spans) {
    body = highlightSpan(body, span);
  }
  return (
    <p
      style={{
        margin: 0,
        whiteSpace: "pre-wrap",
        fontSize: "0.88rem",
        lineHeight: 1.55,
      }}
    >
      {body}
    </p>
  );
}

function highlightSpan(node: React.ReactNode, needle: string): React.ReactNode {
  if (typeof node !== "string") {
    if (Array.isArray(node)) {
      return node.map((n, i) => (
        <span key={i}>{highlightSpan(n, needle)}</span>
      ));
    }
    return node;
  }
  const idx = node.indexOf(needle);
  if (idx < 0) return node;
  return (
    <>
      {node.slice(0, idx)}
      <mark
        style={{
          background: "#fef9c3",
          padding: "0 0.15rem",
          borderRadius: 3,
        }}
      >
        {needle}
      </mark>
      {node.slice(idx + needle.length)}
    </>
  );
}

function triageBtn(color: string, disabled: boolean): React.CSSProperties {
  return {
    padding: "0.3rem 0.65rem",
    borderRadius: 5,
    border: `1px solid ${color}55`,
    background: disabled ? "#f4f4f0" : "#fff",
    color: disabled ? "rgba(0,0,0,0.4)" : color,
    fontSize: "0.78rem",
    cursor: disabled ? "default" : "pointer",
  };
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.max(0, Math.floor(seconds % 60));
  return `${m}:${s.toString().padStart(2, "0")}`;
}
