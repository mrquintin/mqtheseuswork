"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
} from "react";
import {
  listFollowupMessages,
  streamFollowup,
} from "@/lib/currentsApi";
import type {
  PublicCitation,
  PublicFollowupMessage,
} from "@/lib/currentsTypes";
import { renderSafeMarkdown } from "@/lib/safeMarkdown";
import {
  loadSessionId,
  saveSessionId,
} from "@/lib/followupSession";

// Client-side rate limit between sends, in ms. The server enforces its own
// (much stricter) limit — this just keeps eager double-clicks from firing.
const SEND_COOLDOWN_MS = 2000;

// Minimum cosmetic textarea height (1 line) and maximum (~6 lines).
const TEXTAREA_MIN = 38;
const TEXTAREA_MAX = 160;

type LocalMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: PublicCitation[];
  refused: boolean;
  refusal_reason: string | null;
  // Optional presentational flag so error frames render with a tint.
  isError?: boolean;
};

type Pending = {
  text: string;
  citations: PublicCitation[];
} | null;

export function FollowupChat({ opinionId }: { opinionId: string }) {
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [pending, setPending] = useState<Pending>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [inlineError, setInlineError] = useState<string | null>(null);

  const sessionIdRef = useRef<string | null>(null);
  const lastSentAtRef = useRef<number>(0);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const listEndRef = useRef<HTMLDivElement | null>(null);

  // Load session + history on mount. Never auto-ask.
  useEffect(() => {
    const sid = loadSessionId(opinionId);
    if (!sid) return;
    sessionIdRef.current = sid;
    let cancelled = false;
    (async () => {
      try {
        const history = await listFollowupMessages(opinionId, sid);
        if (cancelled) return;
        setMessages(
          history.map((m: PublicFollowupMessage) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            citations: m.citations,
            refused: m.refused,
            refusal_reason: m.refusal_reason,
          })),
        );
      } catch {
        // If history fails (e.g. TTL expired), silently drop the session;
        // the user can still start a new conversation.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [opinionId]);

  // Auto-scroll to bottom when messages or pending text change.
  useEffect(() => {
    listEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, pending?.text, pending?.citations.length]);

  // Auto-grow textarea height.
  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(Math.max(el.scrollHeight, TEXTAREA_MIN), TEXTAREA_MAX);
    el.style.height = `${next}px`;
  }, []);

  useEffect(() => {
    resizeTextarea();
  }, [input, resizeTextarea]);

  const onInputChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
  };

  const send = useCallback(async () => {
    const question = input.trim();
    if (!question) return;
    if (busy) return;

    const now = Date.now();
    if (now - lastSentAtRef.current < SEND_COOLDOWN_MS) {
      setInlineError(
        "Slow down — wait a couple of seconds between messages.",
      );
      return;
    }
    lastSentAtRef.current = now;
    setInlineError(null);

    const userLocal: LocalMessage = {
      id: `local-user-${now}`,
      role: "user",
      content: question,
      citations: [],
      refused: false,
      refusal_reason: null,
    };
    setMessages((prev) => [...prev, userLocal]);
    setInput("");
    setBusy(true);
    setPending({ text: "", citations: [] });

    try {
      const body: { question: string; session_id?: string } = { question };
      if (sessionIdRef.current) body.session_id = sessionIdRef.current;

      let accText = "";
      const accCitations: PublicCitation[] = [];
      let finalRefused = false;
      let finalReason: string | null = null;
      let sawError: string | null = null;

      for await (const frame of streamFollowup(opinionId, body)) {
        if (frame.kind === "meta") {
          sessionIdRef.current = frame.data.session_id;
          saveSessionId(opinionId, frame.data.session_id);
        } else if (frame.kind === "token") {
          accText += frame.data;
          setPending({ text: accText, citations: [...accCitations] });
        } else if (frame.kind === "citation") {
          accCitations.push(frame.data);
          setPending({ text: accText, citations: [...accCitations] });
        } else if (frame.kind === "done") {
          finalRefused = frame.data.refused;
          finalReason = frame.data.refusal_reason;
        } else if (frame.kind === "error") {
          sawError =
            frame.data.reason ||
            frame.data.error ||
            "The firm could not answer that follow-up.";
        }
      }

      if (sawError) {
        setMessages((prev) => [
          ...prev,
          {
            id: `local-err-${Date.now()}`,
            role: "assistant",
            content: sawError ?? "Error.",
            citations: [],
            refused: false,
            refusal_reason: null,
            isError: true,
          },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            id: `local-asst-${Date.now()}`,
            role: "assistant",
            content: accText,
            citations: accCitations,
            refused: finalRefused,
            refusal_reason: finalReason,
          },
        ]);
      }
    } catch (e) {
      const status = (e as { status?: number } | null)?.status;
      const copy =
        status === 429
          ? "You've hit the follow-up rate limit. Try again in a few minutes."
          : "Couldn't reach the firm. Try again in a moment.";
      setMessages((prev) => [
        ...prev,
        {
          id: `local-err-${Date.now()}`,
          role: "assistant",
          content: copy,
          citations: [],
          refused: false,
          refusal_reason: null,
          isError: true,
        },
      ]);
    } finally {
      setPending(null);
      setBusy(false);
    }
  }, [input, busy, opinionId]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
    // Shift+Enter: allow the native newline insertion.
  };

  const hasAny = messages.length > 0 || pending !== null;

  return (
    <div data-testid="followup-chat" style={chatRoot}>
      <div data-testid="followup-messages" style={listStyle} role="log">
        {hasAny ? null : (
          <p style={emptyStyle}>
            Ask the firm a follow-up. It will answer strictly from its
            published Noosphere, cite the sources it relied on, and abstain
            when it does not hold a supported view.
          </p>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {pending ? <PendingBubble pending={pending} /> : null}
        <div ref={listEndRef} />
      </div>

      {inlineError ? (
        <div data-testid="followup-inline-error" style={inlineErrorStyle}>
          {inlineError}
        </div>
      ) : null}

      <form
        data-testid="followup-form"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
        style={formStyle}
      >
        <textarea
          ref={textareaRef}
          data-testid="followup-input"
          aria-label="Ask a follow-up"
          placeholder="Ask a follow-up…"
          value={input}
          onChange={onInputChange}
          onKeyDown={onKeyDown}
          rows={1}
          style={textareaStyle}
          disabled={busy}
        />
        <button
          type="submit"
          data-testid="followup-send"
          disabled={busy || input.trim().length === 0}
          style={sendButtonStyle}
        >
          {busy ? "Asking…" : "Send"}
        </button>
      </form>
    </div>
  );
}

function MessageBubble({ message }: { message: LocalMessage }) {
  const isUser = message.role === "user";
  const isError = !!message.isError;
  return (
    <div
      data-testid={isUser ? "followup-user-msg" : "followup-asst-msg"}
      data-role={message.role}
      style={{
        ...bubbleStyle,
        ...(isUser ? userBubbleStyle : assistantBubbleStyle),
        ...(isError ? errorBubbleStyle : null),
      }}
    >
      {isUser ? (
        // NOTE: user input is untrusted — render as plain text, never markdown.
        <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>
      ) : (
        <>
          <div style={{ lineHeight: 1.55 }}>
            {renderSafeMarkdown(message.content)}
          </div>
          {message.refused ? (
            <div data-testid="followup-refused" style={refusedStyle}>
              The firm abstained from answering
              {message.refusal_reason ? `: ${message.refusal_reason}` : "."}
            </div>
          ) : null}
          {message.citations.length > 0 ? (
            <CitationChips citations={message.citations} />
          ) : null}
        </>
      )}
    </div>
  );
}

function PendingBubble({ pending }: { pending: NonNullable<Pending> }) {
  return (
    <div
      data-testid="followup-pending"
      style={{ ...bubbleStyle, ...assistantBubbleStyle }}
    >
      {pending.text.length === 0 ? (
        <TypingDots />
      ) : (
        <div style={{ lineHeight: 1.55 }}>
          {renderSafeMarkdown(pending.text)}
        </div>
      )}
      {pending.citations.length > 0 ? (
        <CitationChips citations={pending.citations} />
      ) : null}
    </div>
  );
}

function CitationChips({ citations }: { citations: PublicCitation[] }) {
  // Stable keys even when the same source is cited twice.
  const items = useMemo(
    () =>
      citations.map((c, i) => ({
        key: `${c.source_id}-${i}`,
        citation: c,
      })),
    [citations],
  );
  return (
    <div
      data-testid="followup-citations"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.35rem",
        marginTop: "0.5rem",
      }}
    >
      {items.map(({ key, citation }, i) => (
        <a
          key={key}
          data-testid="followup-citation-chip"
          href={`#src-${encodeURIComponent(citation.source_id)}`}
          style={chipStyle}
          title={citation.quoted_span}
        >
          [{i + 1}] {citation.source_kind === "claim" ? "claim" : "conclusion"}
        </a>
      ))}
    </div>
  );
}

function TypingDots() {
  return (
    <span data-testid="followup-typing" aria-label="typing" style={dotsRoot}>
      <span style={{ ...dot, animationDelay: "0s" }}>·</span>
      <span style={{ ...dot, animationDelay: "0.15s" }}>·</span>
      <span style={{ ...dot, animationDelay: "0.3s" }}>·</span>
    </span>
  );
}

// --- styles -----------------------------------------------------------------

const chatRoot: React.CSSProperties = {
  marginTop: "0.75rem",
  display: "flex",
  flexDirection: "column",
  gap: "0.5rem",
};

const listStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "0.5rem",
  maxHeight: "24rem",
  overflowY: "auto",
  paddingRight: "0.25rem",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  fontSize: "0.82rem",
  fontStyle: "italic",
  color: "var(--currents-parchment-dim)",
};

const bubbleStyle: React.CSSProperties = {
  padding: "0.6rem 0.8rem",
  borderRadius: 6,
  fontSize: "0.88rem",
  maxWidth: "92%",
};

const userBubbleStyle: React.CSSProperties = {
  alignSelf: "flex-end",
  background: "var(--currents-surface)",
  border: "1px solid var(--currents-border)",
  color: "var(--currents-parchment)",
};

const assistantBubbleStyle: React.CSSProperties = {
  alignSelf: "flex-start",
  background: "var(--currents-bg-elevated)",
  border: "1px solid var(--currents-border)",
  color: "var(--currents-parchment)",
};

const errorBubbleStyle: React.CSSProperties = {
  borderColor: "var(--currents-amber, #c79a3a)",
  color: "var(--currents-amber, #c79a3a)",
  fontStyle: "italic",
};

const refusedStyle: React.CSSProperties = {
  marginTop: "0.4rem",
  fontSize: "0.78rem",
  fontStyle: "italic",
  color: "var(--currents-amber, #c79a3a)",
};

const chipStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "0.15rem 0.5rem",
  fontSize: "0.72rem",
  letterSpacing: "0.04em",
  borderRadius: 999,
  border: "1px solid var(--currents-border)",
  background: "var(--currents-surface)",
  color: "var(--currents-parchment)",
  textDecoration: "none",
};

const inlineErrorStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  color: "var(--currents-amber, #c79a3a)",
  fontStyle: "italic",
};

const formStyle: React.CSSProperties = {
  display: "flex",
  gap: "0.5rem",
  alignItems: "flex-end",
};

const textareaStyle: React.CSSProperties = {
  flex: 1,
  resize: "none",
  minHeight: `${TEXTAREA_MIN}px`,
  maxHeight: `${TEXTAREA_MAX}px`,
  padding: "0.55rem 0.65rem",
  borderRadius: 4,
  border: "1px solid var(--currents-border)",
  background: "var(--currents-surface)",
  color: "var(--currents-parchment)",
  fontFamily: "inherit",
  fontSize: "0.88rem",
  lineHeight: 1.4,
};

const sendButtonStyle: React.CSSProperties = {
  padding: "0.5rem 0.9rem",
  borderRadius: 4,
  border: "1px solid var(--currents-border)",
  background: "var(--currents-bg-elevated)",
  color: "var(--currents-parchment)",
  fontSize: "0.82rem",
  cursor: "pointer",
};

const dotsRoot: React.CSSProperties = {
  display: "inline-flex",
  gap: "0.2rem",
  fontSize: "1.2rem",
  lineHeight: 1,
  color: "var(--currents-parchment-dim)",
};

const dot: React.CSSProperties = {
  display: "inline-block",
};
