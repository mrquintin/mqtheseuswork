"use client";

import { useState } from "react";

import type { AlignmentRow } from "./PrincipleAlignmentTable";

/**
 * "Sketch a memo" — drafts an investment-committee memo from the
 * principle-alignment table. The draft is intentionally labelled
 * DRAFT and is NEVER auto-promoted: the partner reads, edits, signs.
 *
 * The drafting is a client-side templating step over rows the server
 * already produced; we do not call the LLM here. Keeping memo draft
 * generation deterministic makes the surface auditable and removes
 * the dependency on a network call for the operator workflow.
 *
 * Status: COMMITTING the final memo body is out of scope for this
 * component — the API hook is wired in the deal route handlers.
 */
export default function MemoDrafter({
  dealId,
  dealName,
  alignment,
  existingDraft,
  existingFinal,
}: {
  dealId: string;
  dealName: string;
  alignment: AlignmentRow[];
  existingDraft: string;
  existingFinal: string;
}) {
  const [draft, setDraft] = useState<string>(
    existingDraft || existingFinal || "",
  );
  const [generated, setGenerated] = useState<boolean>(Boolean(existingDraft));

  function buildDraft(): string {
    const matches = alignment.filter((a) => a.verdict === "MATCH");
    const conflicts = alignment.filter((a) => a.verdict === "CONFLICT");
    const unclear = alignment.filter((a) => a.verdict === "UNCLEAR");

    const lines: string[] = [];
    lines.push(`# DRAFT — Investment Memo · ${dealName}`);
    lines.push("");
    lines.push(
      "_This is an agent-generated DRAFT. The partner reads, edits, and signs._",
    );
    lines.push("");
    lines.push("## Principles in support");
    if (matches.length === 0) {
      lines.push("- (none surfaced)");
    } else {
      for (const m of matches) {
        lines.push(`- **${m.principleText}** — ${m.rationale}`);
        for (const c of m.citations) {
          lines.push(`  > “${c.quote}”`);
        }
      }
    }
    lines.push("");
    lines.push("## Principles in tension");
    if (conflicts.length === 0) {
      lines.push("- (none surfaced)");
    } else {
      for (const c of conflicts) {
        lines.push(`- **${c.principleText}** — ${c.rationale}`);
        for (const ct of c.citations) {
          lines.push(`  > “${ct.quote}”`);
        }
      }
    }
    lines.push("");
    lines.push("## Principles with insufficient signal");
    if (unclear.length === 0) {
      lines.push("- (none)");
    } else {
      for (const u of unclear) {
        lines.push(`- ${u.principleText}`);
      }
    }
    lines.push("");
    lines.push("## Partner sign-off");
    lines.push("> _Replace this paragraph with the partner's decision._");
    return lines.join("\n");
  }

  return (
    <div data-testid="memo-drafter" data-deal-id={dealId}>
      <div
        style={{
          display: "flex",
          gap: "0.6rem",
          alignItems: "center",
          marginBottom: "0.7rem",
        }}
      >
        <button
          type="button"
          data-testid="memo-drafter-generate"
          onClick={() => {
            setDraft(buildDraft());
            setGenerated(true);
          }}
          style={{
            padding: "0.5rem 0.9rem",
            background: "transparent",
            color: "var(--amber)",
            border: "1px solid var(--amber)",
            fontFamily: "'Cinzel', serif",
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            fontSize: "0.7rem",
            cursor: "pointer",
          }}
        >
          {generated ? "Re-draft" : "Sketch a memo"}
        </button>
        <span
          className="mono"
          style={{
            fontSize: "0.65rem",
            letterSpacing: "0.14em",
            color: "var(--parchment-dim)",
          }}
        >
          DRAFT only — partner edits + signs
        </span>
      </div>
      <textarea
        data-testid="memo-drafter-textarea"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={Math.max(10, draft.split("\n").length)}
        style={{
          width: "100%",
          background: "rgba(20,16,8,0.55)",
          color: "var(--parchment)",
          border: "1px solid rgba(180,150,80,0.2)",
          padding: "0.8rem",
          fontFamily: "'EB Garamond', serif",
          fontSize: "0.95rem",
          lineHeight: 1.5,
        }}
      />
    </div>
  );
}
