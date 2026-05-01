"use client";

import { useState } from "react";
import { Save, Send, ShieldX, XCircle } from "lucide-react";

import AnswerMarkdown from "@/components/AnswerMarkdown";

import {
  approveAndPostAction,
  killSubstackOutboundAction,
  killXOutboundAction,
  rejectPostAction,
  saveDraftAction,
} from "../actions";

type ReviewPost = {
  id: string;
  body: string;
  subject: string | null;
  markdownBody: string | null;
  status: string;
  externalId: string | null;
  postedAt: string | null;
};

export function XReviewBlock({
  post,
  sourceUrl,
}: {
  post: ReviewPost;
  sourceUrl: string | null;
}) {
  const [body, setBody] = useState(post.body);
  const editable = post.status !== "posted";
  const weightedLength = weightedXLength(body);

  return (
    <section style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 28rem), 1fr))" }}>
      <form className="portal-card" style={{ display: "grid", gap: "0.75rem", padding: "1rem" }}>
        <input name="postId" type="hidden" value={post.id} />
        <ScopedKillCard action={killXOutboundAction} label="KILL - disable X outbound" testId="x-kill-button" />
        {sourceUrl ? (
          <a className="mono" href={sourceUrl} rel="noopener noreferrer" style={{ color: "var(--gold)", fontSize: "0.68rem" }} target="_blank">
            {sourceUrl}
          </a>
        ) : (
          <span className="mono" style={{ color: "var(--ember)", fontSize: "0.68rem" }}>
            No source link
          </span>
        )}
        <TextArea
          label="Post body"
          name="body"
          onChange={setBody}
          readOnly={!editable}
          rows={8}
          value={body}
        />
        <div className="mono" style={{ color: weightedLength > 280 ? "var(--ember)" : "var(--parchment-dim)", fontSize: "0.66rem" }}>
          {weightedLength}/280 weighted chars
        </div>
        {editable ? <EditorActions approveLabel="Approve & post" testId="x-approve-publish" /> : <PostedState post={post} />}
      </form>

      <article className="portal-card" style={{ alignSelf: "start", display: "grid", gap: "0.7rem", padding: "1rem" }}>
        <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem", letterSpacing: "0.18em", margin: 0, textTransform: "uppercase" }}>
          Mocked X preview
        </p>
        <div style={{ border: "1px solid rgba(232, 225, 211, 0.14)", borderRadius: 8, display: "grid", gap: "0.7rem", padding: "0.9rem" }}>
          <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.72rem" }}>
            Theseus Codex @theseus
          </div>
          <p style={{ color: "var(--parchment)", lineHeight: 1.5, margin: 0, whiteSpace: "pre-wrap" }}>{body}</p>
          <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.64rem" }}>
            Founder-approved outbound draft
          </div>
        </div>
      </article>
    </section>
  );
}

export function SubstackReviewBlock({ post }: { post: ReviewPost }) {
  const [subject, setSubject] = useState(post.subject || "");
  const [subtitle, setSubtitle] = useState(post.body);
  const [markdown, setMarkdown] = useState(post.markdownBody || "");
  const editable = post.status !== "posted";

  return (
    <form style={{ display: "grid", gap: "1rem" }}>
      <input name="postId" type="hidden" value={post.id} />
      <section style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 28rem), 1fr))" }}>
        <div className="portal-card" style={{ display: "grid", gap: "0.75rem", padding: "1rem" }}>
          <ScopedKillCard action={killSubstackOutboundAction} label="KILL - disable Substack outbound" testId="substack-kill-button" />
          <Field label="Subject" name="subject" onChange={setSubject} readOnly={!editable} value={subject} />
          <TextArea label="Subtitle" name="body" onChange={setSubtitle} readOnly={!editable} rows={3} value={subtitle} />
          <TextArea label="Markdown body" name="markdownBody" onChange={setMarkdown} readOnly={!editable} rows={22} value={markdown} />
        </div>
        <article className="portal-card" style={{ minWidth: 0, padding: "1rem" }}>
          <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem", letterSpacing: "0.18em", margin: "0 0 0.75rem", textTransform: "uppercase" }}>
            Live Substack preview
          </p>
          <h2 style={{ color: "var(--amber)", fontFamily: "'Cinzel', serif", fontSize: "1.2rem", margin: "0 0 0.4rem" }}>
            {subject || "Untitled draft"}
          </h2>
          <p style={{ color: "var(--parchment-dim)", lineHeight: 1.5, margin: "0 0 0.9rem" }}>
            {subtitle || "No subtitle"}
          </p>
          <AnswerMarkdown>{markdown}</AnswerMarkdown>
        </article>
      </section>
      <section className="portal-card" style={{ color: "var(--parchment-dim)", display: "grid", gap: "0.35rem", padding: "0.85rem" }}>
        <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.62rem", letterSpacing: "0.18em", margin: 0, textTransform: "uppercase" }}>
          Expected delivery
        </p>
        <p style={{ margin: 0 }}>
          Email-to-post draft using the configured Substack publishing address; subject becomes the Substack title and markdown becomes the post body.
        </p>
      </section>
      {editable ? <EditorActions approveLabel="Approve & publish" testId="substack-approve-publish" /> : <PostedState post={post} testId="substack-posted-state" />}
    </form>
  );
}

function ScopedKillCard({
  action,
  label,
  testId,
}: {
  action: () => Promise<void>;
  label: string;
  testId: string;
}) {
  return (
    <div style={{ border: "1px solid rgba(185, 92, 92, 0.65)", borderRadius: 6, padding: "0.65rem" }}>
      <button
        className="btn"
        data-testid={testId}
        formAction={action}
        style={{ borderColor: "rgba(185, 92, 92, 0.95)", color: "var(--ember)" }}
        type="submit"
      >
        <ShieldX aria-hidden="true" size={16} /> {label}
      </button>
    </div>
  );
}

function EditorActions({
  approveLabel,
  testId,
}: {
  approveLabel: string;
  testId: string;
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.55rem" }}>
      <button className="btn" formAction={saveDraftAction} type="submit">
        <Save aria-hidden="true" size={15} /> Save edit
      </button>
      <button className="btn" data-testid={testId} formAction={approveAndPostAction} type="submit">
        <Send aria-hidden="true" size={15} /> {approveLabel}
      </button>
      <button className="btn" formAction={rejectPostAction} style={{ color: "var(--ember)" }} type="submit">
        <XCircle aria-hidden="true" size={15} /> Reject
      </button>
    </div>
  );
}

function Field({
  label,
  name,
  onChange,
  readOnly,
  value,
}: {
  label: string;
  name: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  value: string;
}) {
  return (
    <label className="mono" style={labelStyle}>
      {label}
      <input
        name={name}
        onChange={(event) => onChange(event.currentTarget.value)}
        readOnly={readOnly}
        style={inputStyle}
        value={value}
      />
    </label>
  );
}

function TextArea({
  label,
  name,
  onChange,
  readOnly,
  rows,
  value,
}: {
  label: string;
  name: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  rows: number;
  value: string;
}) {
  return (
    <label className="mono" style={labelStyle}>
      {label}
      <textarea
        name={name}
        onChange={(event) => onChange(event.currentTarget.value)}
        readOnly={readOnly}
        rows={rows}
        style={textareaStyle}
        value={value}
      />
    </label>
  );
}

function PostedState({ post, testId }: { post: ReviewPost; testId?: string }) {
  return (
    <p className="mono" data-testid={testId} style={{ color: "var(--parchment-dim)", fontSize: "0.68rem", margin: 0 }}>
      externalId: {post.externalId || "n/a"} / postedAt: {post.postedAt || "n/a"}
    </p>
  );
}

function weightedXLength(text: string): number {
  const urlRe = /https:\/\/[^\s<>()]+/gi;
  let total = 0;
  let cursor = 0;
  for (const match of text.matchAll(urlRe)) {
    const index = match.index ?? 0;
    total += Array.from(text.slice(cursor, index)).length;
    total += 23;
    cursor = index + match[0].length;
  }
  total += Array.from(text.slice(cursor)).length;
  return total;
}

const labelStyle = {
  color: "var(--amber-dim)",
  display: "grid",
  fontSize: "0.62rem",
  gap: "0.35rem",
  letterSpacing: "0.16em",
  textTransform: "uppercase" as const,
};

const inputStyle = {
  background: "rgba(0,0,0,0.22)",
  border: "1px solid rgba(232, 225, 211, 0.16)",
  borderRadius: 6,
  color: "var(--parchment)",
  font: "inherit",
  letterSpacing: 0,
  padding: "0.7rem",
  textTransform: "none" as const,
};

const textareaStyle = {
  ...inputStyle,
  lineHeight: 1.5,
  resize: "vertical" as const,
};
