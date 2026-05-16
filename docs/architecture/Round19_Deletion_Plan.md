# Round 19 Deletion Plan — Execution Steps

**Source audit:** [`Round19_Deletion_Audit.md`](./Round19_Deletion_Audit.md)
**Status:** AWAITING FOUNDER SIGN-OFF. No code has been changed. Execution begins only after the audit is approved.

This document is the operational complement to the audit. For each item flagged DELETE or DEMOTE in the audit, this plan records:
- The file paths to touch.
- The dependent imports / references found by grep.
- The migration steps (what gets replaced; where 410-Gone handlers go; what redirects fire).
- The reversibility path (how to restore the surface if the deletion turns out to be wrong).

The execution is a single PR. Tests in `theseus-codex/__tests__/round19_deletion_invariants.test.ts` (new file) lock in the invariants.

---

## DELETE items

### 1. Public `/critiques` page

**Path(s):**
- `theseus-codex/src/app/critiques/page.tsx`

**Dependent references (grep):**
- `theseus-codex/src/lib/critiquesApi.ts` — KEEP; still used by `(authed)/critiques/queue/page.tsx` if that survives (it doesn't; see item 3). After item 3 lands, `critiquesApi.ts` is also a delete candidate — fold into this PR.
- `theseus-codex/src/components/ChallengeThisCta.tsx` — links to `/critiques`. Rewrite link to `/about#critiques` (where the policy is stated) or remove the CTA component depending on usage.
- `theseus-codex/src/lib/readerTour.ts` — references `/critiques` step. Remove that step.
- `theseus-codex/src/__tests__/methodology-explorer-v2.test.tsx` + `__snapshots__` — references the route; update snapshots.

**Migration steps:**
1. Delete `theseus-codex/src/app/critiques/page.tsx`.
2. Replace with `theseus-codex/src/app/critiques/route.ts` returning 410 Gone with a body linking `/about#critiques` (or to the new external-critique inbox if that ships).
3. Strip `/critiques` link from `ChallengeThisCta.tsx`; if the component is dead after that, delete it.
4. Remove the reader-tour step.
5. Regenerate snapshots.

**Reversibility:** `git revert` of this PR restores the file. The 410 handler is one-liner.

---

### 2. Public `/revisions` index

**Path(s):**
- `theseus-codex/src/app/revisions/page.tsx`

**KEEP:** `theseus-codex/src/app/revisions/[id]/page.tsx` — detail pages render real data.

**Dependent references (grep):**
- `theseus-codex/src/lib/revisionApi.ts` — KEEP (powers `[id]` detail).
- `theseus-codex/src/lib/lineage-server.ts` — KEEP.

**Migration steps:**
1. Delete `theseus-codex/src/app/revisions/page.tsx`.
2. Add `theseus-codex/src/app/revisions/route.ts` returning 410 with a link to the homepage or the most-recent revision detail.
3. Update any internal nav that links to `/revisions` index — point at the homepage's "Latest revisions" section if it exists, otherwise remove the link.

**Reversibility:** Restore via `git revert`. Detail pages remain accessible throughout.

---

### 3. Authed `/critiques/*` (the operator critique queue)

**Path(s):**
- `theseus-codex/src/app/(authed)/critiques/[id]/` (whole subtree)
- `theseus-codex/src/app/(authed)/critiques/queue/`
- `theseus-codex/src/app/(authed)/critiques/actions.ts`

**Dependent references (grep):**
- `theseus-codex/src/__tests__/critique-pilot.test.ts` — likely exercises this surface; update or remove.
- `theseus-codex/src/lib/critiquesApi.ts` — fold delete into this item (the only consumer is the route being deleted).
- Any primary-nav link to `/critiques` (operator nav). Remove.

**Migration steps:**
1. Delete the subtree.
2. Delete `critiquesApi.ts` after confirming no other consumer.
3. Remove operator-nav entry.
4. Update / delete `critique-pilot.test.ts` to no longer reach into the deleted module.
5. Public `/api/public/critique/submit/route.ts` STAYS (public-side endpoint that accepts critiques into the DB). The operator UI that processes them is gone; the model `CritiqueSubmission` is KEPT. Processing happens via direct DB or a future operator surface.

**Reversibility:** Restore via `git revert`. Pending critique-submissions remain in the DB; only the operator UI is gone.

---

### 4. Prisma model `DealPrincipleAlignment`

**Path(s):**
- `theseus-codex/prisma/schema.prisma` — the `model DealPrincipleAlignment { ... }` block.
- `theseus-codex/prisma/migrations/20260515160000_deals_table/migration.sql` — the table-create statement is here. Do NOT modify this file (migrations are append-only).

**Dependent references (grep across whole repo):**
- `theseus-codex/prisma/schema.prisma` (definition)
- `theseus-codex/prisma/migrations/20260515160000_deals_table/migration.sql` (create)
- `noosphere/alembic/versions/012_deals_table.py` (mirror migration)
- No Python module reads or writes it.
- No TypeScript module reads or writes it.

**Migration steps:**
1. Remove the `model DealPrincipleAlignment { ... }` block from `schema.prisma`.
2. Remove the `dealPrincipleAlignments` relation field from `Deal` (if present) and `Principle` (if present).
3. Add a new Prisma migration `theseus-codex/prisma/migrations/<timestamp>_deprecate_deal_principle_alignment/migration.sql`:
   ```sql
   -- Round 19 deletion pass: code surface removed, table preserved 90 days for audit.
   COMMENT ON TABLE "DealPrincipleAlignment" IS 'DEPRECATED 2026-05-16 (Round 19). Drop scheduled for 2026-08-14.';
   -- (no DROP TABLE; physical drop scheduled for a later round.)
   ```
4. Mirror the same comment in the Alembic chain so cross-DB tooling agrees.
5. Run `pnpm prisma generate` to drop the model from the generated client.

**Reversibility:** Add the model block back to `schema.prisma`. Table is intact for 90 days; data is recoverable.

---

### 5. Prisma model `SubscriberBounce`

**Path(s):**
- `theseus-codex/prisma/schema.prisma` — the `model SubscriberBounce { ... }` block.
- Migrations: do NOT modify; emit a new deprecation migration.

**Dependent references (grep):**
- `theseus-codex/prisma/schema.prisma` (definition).
- `noosphere/scripts/run_first_digest.sh:25` — operator-doc comment only. Update the comment to note the model is deprecated.

**Migration steps:**
1. Remove the model block and any inverse relations from `Subscriber`.
2. Emit deprecation migration (same shape as item 4).
3. Update the shell-script comment.

**Reversibility:** Same shape as item 4.

---

### 6–9. Deprecated noosphere coherence layers

#### 6. `noosphere/coherence/argumentation.py` (Layer 2 — Dung voting)

**Dependent references (grep):**
- `noosphere/noosphere/coherence/__init__.py` (deprecation re-export).
- `noosphere/noosphere/coherence/aggregator.py` (legacy 6-layer aggregator).
- `noosphere/noosphere/methods/_legacy/six_layer_coherence.py` (legacy method wrapper).
- No test directly imports it.

**Migration steps:**
1. Delete the file.
2. Edit `__init__.py` to remove `from .argumentation import …` line; keep only the surviving re-exports (`geometry.hoyer_sparsity`, `nli.StubNLIScorer`, `engine` shim).
3. Edit `aggregator.py` to drop the import. The aggregator path will fail loudly if it is still invoked — that is intentional, since the aggregator itself is being DEMOTED (see DEMOTE section). To avoid a runtime break, gate the aggregator behind a `raise DeprecationWarning('six-layer aggregator retired by Round 19')` at module top.
4. Edit `methods/_legacy/six_layer_coherence.py` similarly — register the method as `retired` in the method registry so the regression suite stops invoking it.

**Reversibility:** `git revert`.

#### 7. `noosphere/coherence/information.py` (Layer 5 — compression)

Same caller pattern as item 6. Same migration steps. Same reversibility.

#### 8. `noosphere/coherence/probabilistic.py` (Layer 3 — Kolmogorov)

Same caller pattern as item 6. Same migration steps. Same reversibility.

#### 9. `noosphere/coherence/judge.py` (Layer 6 — LLM rationality judge)

**Dependent references (grep):**
- Same as items 6–8 (re-export, aggregator, legacy method).
- **Plus** `noosphere/tests/test_coherence_eval.py:164` — `from noosphere.coherence.judge import run_llm_judge`. Strip the import; mark or delete the test that exercises it (the test belongs to the legacy 6-layer evaluation harness, which is itself being retired).

**Migration steps:** as above, plus update `test_coherence_eval.py` to either skip the legacy-judge block or delete it.

**Reversibility:** `git revert`.

---

## DEMOTE items

DEMOTE work is uniform: move the route's directory from `(authed)/<x>/` to `(authed)/ops/<x>/`, remove the entry from primary nav, add a path redirect from the old URL to the new operator URL (so external bookmarks still resolve, but the surface no longer earns a place in the primary nav).

### Public surface
- `theseus-codex/src/app/dialectic/sessions/[id]/page.tsx` → move under `(authed)/dialectic/sessions/[id]/`. Public path → 410 Gone (sessions are operator artifacts; published outputs already exist as memos / conclusions / currents).

### Authed routes → move under `/(authed)/ops/`
Each line below is one DEMOTE item; the migration recipe is identical for all of them:

- adversarial
- algorithms (operator + queue subroutes)
- cascade
- counterfactual
- decay
- deals
- dialectic
- eval
- extractor
- founders
- knowledge-graph (operator subroute)
- literature
- methodology-review-week
- open-questions
- papers
- peer-review
- portfolio-agents (consolidate into `/portfolio`)
- post-mortem
- provenance
- q (only sub-route is `q/review`)
- research
- scoreboard
- sessions
- social
- source-triage
- subscribers
- voices

**Per-item migration recipe:**
1. `git mv theseus-codex/src/app/(authed)/<name>/ theseus-codex/src/app/(authed)/ops/<name>/`.
2. Update imports in pages/components that reference the old path.
3. Remove the entry from `theseus-codex/src/components/nav/PrimaryNav.tsx` (or whichever primary-nav file is canonical).
4. Add a redirect in `theseus-codex/middleware.ts` (or `next.config.js` redirects): `'/<name>' → '/ops/<name>'` (permanent 308).
5. Verify the test in §D treats the old path as redirected and the new path as authed-only.

**Reversibility:** `git revert` restores both the file move and the nav entry.

### API: `/api/conclusion-deletion-requests/*` → DEMOTE to authed

**Path(s):** `theseus-codex/src/app/api/conclusion-deletion-requests/route.ts` + `[id]/route.ts`.

**Migration:** `git mv` from `src/app/api/conclusion-deletion-requests/` to `src/app/(authed)/api/conclusion-deletion-requests/`. Update any TS-side import paths if present (none found by grep).

**Reversibility:** Move back.

### Prisma model demotions

Eight models (ContradictionDispute, ContradictionLifecycle, ResolutionOverride, ResolutionMismatch, ResolutionRevision, GraphEdgeReasoning, PrincipleClusterCentroid, PrincipleConvictionUpdateQueue, ContradictionTestTask, ClusterReindexProposal). For each:
1. Add a `/// @demoted operator-only — Round 19` comment above the model.
2. Audit `theseus-codex/src/lib/**` for public-surface helpers that query these models; relocate them to operator-only helper files under `src/lib/ops/` or remove them if unused.
3. Add the models to the existing `schema-shape.test.ts` denylist of "models that must not appear in public API surface area".

**Reversibility:** Strip the comment, restore the helpers.

### Noosphere demotions

- `noosphere/coherence/__init__.py` — trim re-exports to the surviving symbols only.
- `noosphere/coherence/engine.py` — raise `DeprecationWarning` at import; mark `__all__` empty; keep file for the regression suite.
- `noosphere/coherence/aggregator.py` — same shape (or move under `noosphere/_legacy/`).
- `noosphere/methods/_legacy/six_layer_coherence.py` — register as `retired` in the method registry; the regression suite skips retired methods unless explicitly opted in.

**Reversibility:** Revert the warning-raise and registry retirement.

---

## Anti-resurrection invariants (test file)

`theseus-codex/__tests__/round19_deletion_invariants.test.ts` asserts:

1. **DELETE routes return 410** when fetched. Iterate over the public delete paths (`/critiques`, `/revisions`) and assert the response status === 410.
2. **DEMOTE routes** only resolve under `(authed)/ops/<name>`, never under `(authed)/<name>` (assert 308 redirect → `/ops/<name>` from the old path).
3. **Deprecated coherence imports** are empty: `from noosphere.coherence import argumentation` raises `ImportError` (or the module simply does not exist). The test asserts the file is absent.
4. **No source file** imports the four DELETEd coherence modules.
5. **Prisma models** `DealPrincipleAlignment` and `SubscriberBounce` do not appear in `Prisma.dmmf.datamodel.models[*].name`.

The test runs in CI; a re-introduction of any deletion would fail the build.

---

## Operator notification (post-execution)

After step C completes, the executor fires a structured log line summarizing the cleanup. Shape:

```
{
  "event": "round19.deletion_pass",
  "audit_doc": "docs/architecture/Round19_Deletion_Audit.md",
  "plan_doc":  "docs/architecture/Round19_Deletion_Plan.md",
  "deleted_routes":   9,
  "deleted_models":   2,
  "deleted_modules":  4,
  "demoted_routes":   27,
  "demoted_models":   10,
  "demoted_modules":  4,
  "completed_at":     "<ISO>"
}
```

Surface: emit via the existing structured-log channel (or `console.log` of JSON if that is the convention) from a one-shot post-deletion script that is run as part of the PR's CI step.

---

## Open questions for the founder

Before execution starts, two judgment calls the audit explicitly leaves to the founder:

1. **Should `(authed)/deals` survive at all,** even DEMOTEd? It is a sidecar to the portfolio surface; portfolio is canonical. DEMOTE is the safe call; DELETE is a legitimate alternative.
2. **The 6-layer coherence regression suite** — keep the legacy method registered so we can prove the new engine is at least as good, OR retire it entirely now? The current plan DEMOTEs (keeps for regression-only); deleting `aggregator.py` + the legacy method outright is an option.

Both are flagged but not committed in this plan. Mark a preference and the plan is revised before any code changes.

---

**Sign-off marker:** When this plan is approved, replace the `Status:` header at the top with the date of sign-off, and execution may begin.
