"use client";

import type { CSSProperties, FormEvent, KeyboardEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { PublicSource } from "@/lib/currentsTypes";
import { loadSession, saveSession } from "@/lib/followupSession";
import {
  FollowupStreamError,
  streamFollowup,
  type FollowupStreamEvent,
} from "@/lib/streamFollowup";
import { renderSafeMarkdown } from "@/lib/safeMarkdown";

const QUESTION_MAX_LENGTH = 1000;
const MIN_SEND_INTERVAL_MS = 2000;

type ChatStatus = "idle" | "awaiting_first_token" | "streaming" | "done" | "error";
type Role = "user" | "assistant";

interface CitationChip {
  id: string;
  href: string;
  sourceId: string;
  sourceKind: string;
}

interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  citations: CitationChip[];
}

interface FollowupChatProps {
  opinionId: string;
  sources: PublicSource[];
  stream?: typeof streamFollowup;
}

function normalizedKind(value: string | null | undefined): string {
  const normalized = value?.trim().toLowerCase() ?? "";
  if (normalized === "conclusion" || normalized === "claim") return normalized;
  return normalized || "source";
}

function fallbackCanonicalPath(source: PublicSource): string {
  const sourceId = encodeURIComponent(source.source_id);
  if (normalizedKind(source.source_kind) === "claim") {
    return `/c/${sourceId}#claim-${sourceId}`;
  }
  return `/c/${sourceId}`;
}

function canonicalPath(source: PublicSource): string {
  return source.canonical_path || fallbackCanonicalPath(source);
}

function sourceIdFromPayload(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) return null;
  const sourceId = (payload as { source_id?: unknown }).source_id;
  return typeof sourceId === "string" && sourceId.trim() ? sourceId : null;
}

function sessionIdFromPayload(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) return null;
  const sessionId = (payload as { session_id?: unknown }).session_id;
  return typeof sessionId === "string" && sessionId.trim() ? sessionId : null;
}

function tokenText(payload: unknown): string {
  if (typeof payload === "string") return payload;
  if (typeof payload !== "object" || payload === null) return "";
  const text = (payload as { text?: unknown }).text;
  return typeof text === "string" ? text : "";
}

function retryAfterLabel(value: string | null): string | null {
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds > 0) {
    return `Retry after ${Math.ceil(seconds)} second${Math.ceil(seconds) === 1 ? "" : "s"}.`;
  }
  return `Retry after ${value}.`;
}

function errorMessage(error: unknown): string {
  if (error instanceof FollowupStreamError) {
    if (error.status === 429) return "Rate limited. Please wait before sending another follow-up.";
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Follow-up request failed.";
}

function citationChipFromPayload(
  payload: unknown,
  sourcesById: Map<string, PublicSource>,
  sequence: number,
): CitationChip | null {
  if (typeof payload !== "object" || payload === null) return null;
  const sourceId = sourceIdFromPayload(payload);
  if (!sourceId) return null;

  const source = sourcesById.get(sourceId);
  if (!source) return null;

  const payloadKind = (payload as { source_kind?: unknown }).source_kind;
  const sourceKind =
    typeof payloadKind === "string" && payloadKind.trim()
      ? normalizedKind(payloadKind)
      : normalizedKind(source.source_kind);

  return {
    id: `${sourceId}-${sequence}`,
    href: canonicalPath(source),
    sourceId,
    sourceKind,
  };
}

const panelStyle: CSSProperties = {
  borderTop: "1px solid var(--currents-border)",
  marginTop: "2rem",
  paddingTop: "1.4rem",
  scrollMarginTop: "1.5rem",
};

const titleStyle: CSSProperties = {
  color: "var(--currents-parchment)",
  fontFamily: "'Cinzel', serif",
  fontSize: "1rem",
  letterSpacing: "0.08em",
  margin: "0 0 0.8rem",
  textTransform: "uppercase",
};

const historyStyle: CSSProperties = {
  display: "grid",
  gap: "0.75rem",
  marginBottom: "0.85rem",
};

const bubbleBaseStyle: CSSProperties = {
  border: "1px solid var(--currents-border)",
  borderRadius: "6px",
  fontSize: "0.95rem",
  lineHeight: 1.55,
  padding: "0.75rem 0.85rem",
};

const userBubbleStyle: CSSProperties = {
  ...bubbleBaseStyle,
  background: "rgba(232, 225, 211, 0.07)",
  color: "var(--currents-parchment)",
  justifySelf: "end",
  maxWidth: "82%",
  whiteSpace: "pre-wrap",
};

const assistantBubbleStyle: CSSProperties = {
  ...bubbleBaseStyle,
  background: "var(--currents-bg-elevated)",
  color: "var(--currents-parchment)",
  justifySelf: "start",
  maxWidth: "88%",
};

const chipStyle: CSSProperties = {
  border: "1px solid var(--currents-border)",
  borderRadius: "999px",
  color: "var(--currents-gold)",
  display: "inline-flex",
  fontSize: "0.78rem",
  lineHeight: 1,
  margin: "0.25rem 0.35rem 0 0",
  padding: "0.32rem 0.5rem",
  textDecoration: "none",
  verticalAlign: "middle",
};

export default function FollowupChat({
  opinionId,
  sources,
  stream = streamFollowup,
}: FollowupChatProps) {
  const sourcesById = useMemo(
    () => new Map(sources.map((source) => [source.source_id, source])),
    [sources],
  );
  const [sessionId, setSessionId] = useState(() => loadSession(opinionId));
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [nextAllowedAt, setNextAllowedAt] = useState(0);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const [retryTooltip, setRetryTooltip] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const messageSequence = useRef(0);

  const isBusy = status === "awaiting_first_token" || status === "streaming";
  const trimmedQuestion = question.trim();
  const waitMs = Math.max(0, nextAllowedAt - nowTick);
  const sendDisabled =
    isBusy ||
    !trimmedQuestion ||
    question.length > QUESTION_MAX_LENGTH ||
    waitMs > 0;

  useEffect(() => {
    setSessionId(loadSession(opinionId));
  }, [opinionId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (waitMs <= 0) return;

    const timer = window.setTimeout(() => {
      setNowTick(Date.now());
    }, waitMs);
    return () => window.clearTimeout(timer);
  }, [waitMs]);

  const focusAsk = useCallback(() => {
    if (typeof window === "undefined" || window.location.hash !== "#ask") return;
    window.setTimeout(() => {
      textareaRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      textareaRef.current?.focus({ preventScroll: true });
    }, 0);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    focusAsk();
    window.addEventListener("hashchange", focusAsk);
    return () => window.removeEventListener("hashchange", focusAsk);
  }, [focusAsk]);

  const nextMessageId = useCallback((prefix: string) => {
    messageSequence.current += 1;
    return `${prefix}-${Date.now()}-${messageSequence.current}`;
  }, []);

  const appendToAssistant = useCallback((assistantId: string, event: FollowupStreamEvent) => {
    if (event.kind === "token") {
      const text = tokenText(event.payload);
      if (!text) return;
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: `${message.content}${text}` }
            : message,
        ),
      );
      setStatus("streaming");
      return;
    }

    if (event.kind === "citation") {
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantId) return message;
          const chip = citationChipFromPayload(
            event.payload,
            sourcesById,
            message.citations.length + 1,
          );
          if (!chip) return message;
          return { ...message, citations: [...message.citations, chip] };
        }),
      );
    }
  }, [sourcesById]);

  const handleSend = useCallback(async () => {
    const normalizedQuestion = question.trim();
    const currentTime = Date.now();

    if (!normalizedQuestion || question.length > QUESTION_MAX_LENGTH || isBusy) return;
    if (currentTime < nextAllowedAt) {
      setNowTick(currentTime);
      setRetryTooltip(`Wait ${Math.ceil((nextAllowedAt - currentTime) / 1000)} seconds before sending again.`);
      return;
    }

    const userMessage: ChatMessage = {
      id: nextMessageId("user"),
      role: "user",
      content: normalizedQuestion,
      citations: [],
    };
    const assistantId = nextMessageId("assistant");
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      citations: [],
    };

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setQuestion("");
    setStatus("awaiting_first_token");
    setRetryTooltip(null);
    setNextAllowedAt(currentTime + MIN_SEND_INTERVAL_MS);
    setNowTick(currentTime);

    try {
      for await (const event of stream(opinionId, normalizedQuestion, sessionId)) {
        if (event.kind === "meta") {
          const streamedSessionId = sessionIdFromPayload(event.payload);
          if (streamedSessionId) {
            saveSession(opinionId, streamedSessionId);
            setSessionId(streamedSessionId);
          }
          continue;
        }

        if (event.kind === "done") {
          setStatus("done");
          continue;
        }

        appendToAssistant(assistantId, event);
      }
    } catch (error) {
      const retryAfter =
        error instanceof FollowupStreamError
          ? retryAfterLabel(error.retryAfter)
          : null;
      setRetryTooltip(retryAfter);
      setStatus("error");
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content: errorMessage(error),
                citations: [],
              }
            : message,
        ),
      );
    }
  }, [
    appendToAssistant,
    isBusy,
    nextAllowedAt,
    nextMessageId,
    opinionId,
    question,
    sessionId,
    stream,
  ]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void handleSend();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    void handleSend();
  };

  const buttonTitle =
    retryTooltip ??
    (waitMs > 0 ? `Wait ${Math.ceil(waitMs / 1000)} seconds before sending again.` : undefined);

  return (
    <section aria-label="Ask a follow-up" id="ask" style={panelStyle}>
      <h2 style={titleStyle}>Ask a follow-up</h2>

      <div aria-live="polite" style={historyStyle}>
        {messages.map((message) =>
          message.role === "user" ? (
            <div key={message.id} style={userBubbleStyle}>
              {message.content}
            </div>
          ) : (
            <div key={message.id} data-role="assistant" style={assistantBubbleStyle}>
              {message.content ? (
                <div>{renderSafeMarkdown(message.content)}</div>
              ) : status === "awaiting_first_token" ? (
                <span aria-label="Assistant is typing" className="followup-typing">
                  <span />
                  <span />
                  <span />
                </span>
              ) : null}
              {message.citations.length ? (
                <span aria-label="Follow-up citations">
                  {message.citations.map((citation) => (
                    <a key={citation.id} href={citation.href} style={chipStyle}>
                      ⸺ {citation.sourceKind}
                    </a>
                  ))}
                </span>
              ) : null}
            </div>
          ),
        )}
      </div>

      <form onSubmit={handleSubmit}>
        <textarea
          aria-label="Follow-up question"
          maxLength={QUESTION_MAX_LENGTH}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about the evidence, uncertainty, or implications."
          ref={textareaRef}
          rows={4}
          style={{
            background: "rgba(0, 0, 0, 0.22)",
            border: "1px solid var(--currents-border)",
            borderRadius: "6px",
            color: "var(--currents-parchment)",
            font: "inherit",
            lineHeight: 1.5,
            padding: "0.75rem",
            resize: "vertical",
            width: "100%",
          }}
          value={question}
        />
        <div
          style={{
            alignItems: "center",
            display: "flex",
            gap: "0.75rem",
            justifyContent: "space-between",
            marginTop: "0.55rem",
          }}
        >
          <span
            style={{
              color:
                question.length >= QUESTION_MAX_LENGTH
                  ? "var(--currents-amber)"
                  : "var(--currents-muted)",
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: "0.74rem",
            }}
          >
            {question.length}/{QUESTION_MAX_LENGTH}
          </span>
          <button
            disabled={sendDisabled}
            style={{
              background: sendDisabled ? "rgba(232, 225, 211, 0.08)" : "var(--currents-gold)",
              border: "1px solid var(--currents-border)",
              borderRadius: "999px",
              color: sendDisabled ? "var(--currents-muted)" : "#14110b",
              cursor: sendDisabled ? "not-allowed" : "pointer",
              fontWeight: 700,
              padding: "0.52rem 0.85rem",
            }}
            title={buttonTitle}
            type="submit"
          >
            Send
          </button>
        </div>
      </form>

      <style>{`
        .followup-typing {
          align-items: center;
          display: inline-flex;
          gap: 0.24rem;
          min-height: 1.5rem;
        }

        .followup-typing span {
          animation: followup-typing-pulse 1s infinite ease-in-out;
          background: var(--currents-muted);
          border-radius: 999px;
          display: block;
          height: 0.36rem;
          opacity: 0.35;
          width: 0.36rem;
        }

        .followup-typing span:nth-child(2) {
          animation-delay: 0.14s;
        }

        .followup-typing span:nth-child(3) {
          animation-delay: 0.28s;
        }

        @keyframes followup-typing-pulse {
          0%, 80%, 100% {
            opacity: 0.35;
            transform: translateY(0);
          }
          40% {
            opacity: 1;
            transform: translateY(-2px);
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .followup-typing span {
            animation: none;
          }
        }
      `}</style>
    </section>
  );
}
