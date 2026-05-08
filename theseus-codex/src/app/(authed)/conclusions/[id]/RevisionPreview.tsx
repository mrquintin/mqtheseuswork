"use client";

/**
 * Revision impact preview modal.
 *
 * Rendered when the founder marks new evidence on a claim from the
 * conclusion detail page. Shows every conclusion that would change,
 * grouped by classification (newly contradicted / newly supported /
 * changed) before the revision is committed.
 *
 * Confirm-to-commit. Cancel reverts the in-memory state and is
 * expected to retract the evidence marker via the parent page's
 * cancel handler.
 *
 * K-cap (REVISION_MAX_AUTOCOMMIT): when affected_count > K we require
 * a typed confirmation phrase ("revise") before the commit button
 * unlocks. The threshold matches the Python engine's default.
 */

import { useMemo, useState } from "react";

import {
  affectedCount,
  REVISION_MAX_AUTOCOMMIT,
  requiresTypedConfirmation,
  type ConfidenceShiftDTO,
  type RevisionPlanDTO,
} from "@/lib/revisionApi";

const TYPED_CONFIRMATION_PHRASE = "revise";

interface Props {
  plan: RevisionPlanDTO;
  conclusionTexts: Record<string, string>;
  onCancel: () => void;
  onConfirm: (typedConfirmation: boolean) => void | Promise<void>;
}

export default function RevisionPreview({
  plan,
  conclusionTexts,
  onCancel,
  onConfirm,
}: Props) {
  const [typed, setTyped] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const needsTyped = requiresTypedConfirmation(plan);
  const total = affectedCount(plan);

  const canConfirm = useMemo(() => {
    if (submitting) return false;
    if (!needsTyped) return true;
    return typed.trim().toLowerCase() === TYPED_CONFIRMATION_PHRASE;
  }, [needsTyped, submitting, typed]);

  async function handleConfirm() {
    setSubmitting(true);
    try {
      await onConfirm(needsTyped);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="revision-preview-title"
      className="revision-preview-modal"
    >
      <div className="revision-preview-card">
        <header>
          <h2 id="revision-preview-title">Revision impact preview</h2>
          <p className="revision-preview-summary">
            {total === 0
              ? "No conclusion shifts more than the δ threshold; revision is a no-op."
              : `${total} conclusion${
                  total === 1 ? "" : "s"
                } would change. ${plan.stableCount} would stay stable.`}
          </p>
        </header>

        <ShiftSection
          title="Newly contradicted"
          tone="negative"
          shifts={plan.newlyContradicted}
          conclusionTexts={conclusionTexts}
        />
        <ShiftSection
          title="Newly supported"
          tone="positive"
          shifts={plan.newlySupported}
          conclusionTexts={conclusionTexts}
        />
        <ShiftSection
          title="Confidence changed"
          tone="neutral"
          shifts={plan.changed}
          conclusionTexts={conclusionTexts}
        />

        {needsTyped ? (
          <div className="revision-preview-typed-confirm">
            <p>
              This revision affects more than{" "}
              {REVISION_MAX_AUTOCOMMIT} conclusions. Type{" "}
              <code>{TYPED_CONFIRMATION_PHRASE}</code> to confirm.
            </p>
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              aria-label="Typed confirmation"
              autoComplete="off"
            />
          </div>
        ) : null}

        <footer className="revision-preview-actions">
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="revision-preview-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!canConfirm}
            className="revision-preview-confirm"
          >
            {submitting ? "Committing…" : "Commit revision"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function ShiftSection({
  title,
  tone,
  shifts,
  conclusionTexts,
}: {
  title: string;
  tone: "positive" | "negative" | "neutral";
  shifts: ConfidenceShiftDTO[];
  conclusionTexts: Record<string, string>;
}) {
  if (shifts.length === 0) return null;
  return (
    <section className={`revision-preview-section revision-preview-${tone}`}>
      <h3>
        {title} ({shifts.length})
      </h3>
      <ul>
        {shifts.map((s) => (
          <li key={s.conclusionId}>
            <span className="revision-preview-text">
              {conclusionTexts[s.conclusionId] ?? s.conclusionId}
            </span>
            <span className="revision-preview-numbers">
              {s.before.toFixed(2)} → {s.after.toFixed(2)} (
              {s.delta >= 0 ? "+" : ""}
              {s.delta.toFixed(2)})
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
