# Reconciliation: UI Critique 2026-05-13 vs. Prompt 54 (Dashboard Terminology Cleanup)

Prompt 54 was the dashboard terminology cleanup pass. The founder
removed the "Attention" box and tightened the library-button wording.
Prompt 66 (this pass) executes the critique in
`UI_CRITIQUE_2026_05_13.md`. Where the two disagree, the rule in the
prompt is:

> Critique wording wins, UNLESS the critique would re-introduce a
> string the founder explicitly removed in prompt 54.

This file documents every place the two passes touch the same surface
or string, and which one was honoured.

---

## R-012 — Dashboard "Now" card

**Critique proposal.** Introduce a single "Now" card at the top of
`/dashboard` with one sentence (e.g. "The firm has 3 new
contradictions; review?") and one primary `ActionButton`. Replaces the
implicit "scan everything" mode.

**Conflict with p54.** Prompt 54 explicitly removed the "Attention"
box (per CLAUDE-tracked founder feedback: it surfaced noise and was
deleted). The critique's "Now" card is *not* the Attention box — its
contract is different (one-sentence, one-button, server-computed
highest-priority item) — but the surface and the vertical real estate
are the same, and the founder may read the "Now" card as the Attention
box returning under a new name.

**Resolution.** **DEFERRED in this pass.** R-012 is held until the
founder confirms the "Now" card is meaningfully different from the
Attention box. The dashboard top-of-body real estate is left as it
stands after prompt 54. See `applied/SUMMARY.md` → R-012 for status.

---

## R-013 — `SignalCard` primitive

**Critique proposal.** A primitive in `components/design/SignalCard.tsx`
that all dashboard cards route through, with `title`, `count`,
`caption`, `footer`.

**Conflict with p54.** None. Prompt 54 deleted the Attention box but
the surviving signal cards (post-p54) are exactly the cards R-013
targets. The primitive is additive — it does not bring back removed
strings — and tightens drift across cards prompt 54 left in place.

**Resolution.** **APPLIED.** The primitive ships in
`components/design/SignalCard.tsx`. Migration of existing dashboard
cards to route through it is left to follow-up work (not this pass)
because prompt 54 already settled the per-card wording.

---

## R-014 — Display-name nudge dismissal persistence

**Critique proposal.** Persist a `dismissed_at` so the nudge does not
re-fire after the user has set their name (regression: it re-rendered
when the display name happened to equal the email local-part).

**Conflict with p54.** None. Prompt 54 did not touch the nudge; it
removed adjacent terminology only. The persistence fix is purely
additive to what p54 left in place.

**Resolution.** **APPLIED.**

---

## Library button wording (cross-cutting)

Prompt 54 settled the library-button label as the canonical form.
The critique does not propose changing the library-button string —
R-001 (lock primary clickables to `PrimaryNavLink`/`ActionButton`)
only locks the *primitive*, not the label. The p54 wording is
preserved.

**Resolution.** No reconciliation needed. The string p54 settled on
remains the displayed string.

---

## Attention box

The Attention box was deleted in prompt 54. No revision in this
critique brings it back. Any "Now"-card-like surface (see R-012
above) is deferred until the founder confirms it is meaningfully
different. The Attention string itself is not re-introduced anywhere
in this pass.
