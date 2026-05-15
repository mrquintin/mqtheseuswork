# UI Critique 2026-05-13 — Refusals

Revisions that this implementation pass attempted but refused after
implementation, because the change would have measurably degraded
accessibility (WCAG AA contrast, keyboard navigation, screen-reader
landmarks) or broken an existing test.

A revision listed here is distinct from one listed as DEFERRED in
`applied/SUMMARY.md`. DEFERRED means "not attempted in this pass";
REFUSED means "attempted, then rejected on a specific quality bar".

The founder reads this file. Refusals are not silent — each entry
states the specific accessibility or test failure that drove the
refusal, and what would need to change for a later pass to retry.

---

*No revisions were refused in the prompt-66 pass.*

Every revision from the critique that was attempted in this pass
either landed (see `applied/SUMMARY.md` → APPLIED) or was deferred
without an implementation attempt (see → DEFERRED). The accessibility
and test gates that would have triggered a refusal were not crossed
by the changes that landed.

If a later pass attempts one of the DEFERRED revisions and discovers
an a11y regression, add the refusal entry here at that point.
