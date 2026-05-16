# Round 19 Deletion Audit — "Every Assumption Fights For Its Life"

**Prompt:** coding_prompts/16_deletion_pass.txt
**Date drafted:** 2026-05-16
**Status:** AWAITING FOUNDER SIGN-OFF. No code has been removed.

---

## Load-bearing question

For every surface in the system, the audit asks one question:

> **"Does this earn its place in the Philosopher-in-a-Box product?"**

Philosopher-in-a-Box = a system that turns the founder's beliefs into algorithm-shaped output, publishes positions, runs forecasts, demonstrates calibration, and lets a reader interrogate the firm's thinking. The founder is the operator. The audience is everyone else.

Verdicts:
- **KEEP** — load-bearing for the Philosopher-in-a-Box surface (founder workflow, public belief delivery, calibration proof, or required infrastructure).
- **DEMOTE** — earns its place as operator observability but does *not* belong in the public/primary nav. Move under `(authed)/ops/*` (operator-only), remove from primary navigation, redirect old path → new.
- **DELETE** — does not earn its place. Code removed. If a route: replaced with a 410 Gone. If a Prisma model: deprecation migration only — physical drop scheduled 90 days out. If a noosphere module: file + tests removed, import surface updated. Reversibility documented in the Plan.

Borderline = DEMOTE or DELETE, not KEEP. The deletion pass is a deliberate act of revealing — what survives is what is most essential.

---

## A. Public routes (`theseus-codex/src/app/`, non-`(authed)/`)

| Route | File | Purpose | Verdict | Justification |
|---|---|---|---|---|
| `/` | `page.tsx` | Landing: latest currents, articles, conclusions, ask box, firm identity. | KEEP | Entry to the published surface. |
| `/about` | `about/page.tsx` | Firm identity, axioms, manifesto, contact form. | KEEP | Public positioning. |
| `/ask` | `ask/page.tsx` | Public RAG question UI. | KEEP | Belief retrieval is the product. |
| `/algorithms` | `algorithms/page.tsx` | Public algorithm catalog (status, calibration). | KEEP | Algorithm-shaped output, externally inspectable. |
| `/calibration` | `calibration/page.tsx` | Public scorecard: Brier, reliability diagram, resolution audit. | KEEP | Calibration is the proof. Load-bearing. |
| `/currents` | `currents/page.tsx` | Live opinion feed; firm responses to events. | KEEP | The published opinion stream. |
| `/forecasts` | `forecasts/page.tsx` | Prediction-market grid with live scoring. | KEEP | Forecast as algorithm output. |
| `/knowledge-graph` | `knowledge-graph/page.tsx` | Cross-source semantic graph (public). | KEEP | Lets readers see how principles/conclusions interrelate. |
| `/library` | `library/page.tsx` | External reading list (endorsed / opposed). | KEEP | Intellectual-honesty surface. |
| `/login` | `login/page.tsx` | Founder authentication gate. | KEEP | Required to reach the operator surface. |
| `/memos` | `memos/page.tsx` | Public memos index. | KEEP | Investment-memo output. |
| `/methodology` | `methodology/page.tsx` | Three-layer methodology explorer. | KEEP | The "reusable part of inquiry" surface. |
| `/post/[slug]` | `post/[slug]/page.tsx` | Published article detail. | KEEP | Where positions live. |
| `/principles` | `principles/page.tsx` | Principles index (conviction, kind, domain). | KEEP | Spine of the firm's knowledge. |
| `/privacy` | `privacy/page.tsx` | Data-retention policy bound to code. | KEEP | Legal + transparency. |
| `/proof` | `proof/page.tsx` | Publication-signature scheme, verification. | KEEP | Cryptographic provenance contract. |
| `/c/[…]` | `c/...` | Conclusion detail (canonical URL). | KEEP | Permalink for published conclusions. |
| `/feed.xml`, `/atom.xml` | `feed.xml/route.ts`, `atom.xml/route.ts` | RSS / Atom of published conclusions. | KEEP | Subscriber protocol. |
| `/not-found.tsx` | `not-found.tsx` | 404 page (Dying-Gladiator ASCII). | KEEP | Branded error. |
| `/layout.tsx` | `layout.tsx` | Root layout, theme bootstrap, skip-link. | KEEP | Infrastructure. |
| `/critiques` | `critiques/page.tsx` | Hall-of-fame for accepted external critiques. | **DELETE** | Empty ceremony: surface promises a workflow that has not yet shipped accepted critiques. Until critiques flow, this is a public commitment masquerading as a product surface. Reversible (restore from git when first critique lands). |
| `/revisions` | `revisions/page.tsx` | Revision-ledger explanatory page. | **DELETE** | The index renders an explanation, not actual revision events. Detail at `/revisions/[event-id]` keeps real data; the index page is scaffolding. |
| `/dialectic` | `dialectic/sessions/[id]/page.tsx` (no index) | Public dialectic-session detail. | **DEMOTE** | The only public dialectic surface is the per-session detail page, which is operator-internal in practice. Move under `(authed)/dialectic/*`, redirect public `/dialectic/sessions/[id]` → 410 (sessions are not public artifacts; published outputs live as memos/conclusions/currents). |
| `/research` | `research/[slug]/page.tsx`, `research/seasonal/[slug]/page.tsx` | Research/seasonal-review public detail. | KEEP | Detail routes render seasonal-review content; the index is intentionally absent. Keep as-is. |

### Founder-targeted items — public surface status

| Target | Status in public surface |
|---|---|
| Manual contradiction-resolution UI | **Gone from public.** No public route exposes a manual resolve action. ✓ |
| "Attention" box on dashboard | **N/A public** (dashboard is authed). No public mirror. ✓ |
| Six contradiction heuristics | **Properly contextualized** as legacy probes inside `/methodology/benchmark/qh/`. Not exposed as a user-facing surface. ✓ |
| First-person-shaped conclusions | **Gone from public.** Surveyed copy is firm-voice / third-person, no "I think X" prose remaining. ✓ |

---

## B. Authed routes (`theseus-codex/src/app/(authed)/`)

KEEPs are the founder's primary workflow surface. DEMOTEs are operator-observability — they keep earning a place, but a private one (under `/ops/`). DELETEs failed the test entirely.

### Founder-targeted items — authed surface status (REPORT FIRST)

1. **Manual contradiction-resolution UI** — `contradictions/contradiction-actions.tsx` no longer exposes "Resolve" / "Dismiss as false positive" buttons; it renders a status badge for legacy rows and a "View lifecycle" link. Source-driven lifecycle (via the engine) is the only resolution path. → **KEEP-as-operator** (the page is observability, not manual mutation). The actions component is a thin shim that should be DEMOTED (read-only, no resolution surface).

2. **"Attention" box on dashboard** — Removed from the dashboard (prompt 54). The `attention/` route still serves an operator queue reachable from the operational signals strip. → **KEEP-as-operator.**

3. **Six contradiction heuristics** — Surface only as legacy radar labels inside `contradictions/page.tsx` (observability of how the legacy engine scored, NOT a production decision surface). → **DEMOTE** the radar visualization to operator-only; the canonical contradiction engine output is already what drives lifecycle.

4. **First-person-shaped conclusions** — `conclusions/page.tsx` renders algorithm-shaped output (text + rationale + confidence tier). → **KEEP.** No first-person prose remains.

### Authed route table

| Route | Verdict | Justification |
|---|---|---|
| `account` | KEEP | Founder profile + passphrase. |
| `admin` | KEEP-as-operator | Only sub-route is `admin/contact` (public contact-form inbox); keep as operator surface. |
| `adversarial` | DEMOTE | Adversarial-challenge triage; operator observability only. |
| `algorithms` | KEEP-as-operator | Operator queue + detail for algorithm distillation. Has no root `page.tsx`; sub-routes only. Move under `/ops/algorithms/*` or remove from primary nav. |
| `ask` | KEEP | Founder RAG query surface. |
| `attention` | KEEP-as-operator | Founder review queue (citations, drift, threads). |
| `captures` | KEEP | Voice-memo → transcript → principle workflow. Founder-facing. |
| `cascade` | DEMOTE | Subsumption observability; operator-only. |
| `codex-ask` | KEEP | Founder-only RAG query (variant of `ask`). |
| `conclusions` | KEEP | Indexed list, tiered (firm / founder / open / retired). |
| `contradictions` | KEEP-as-operator | Observability of coherence + lifecycle. (Manual-resolve actions already removed.) |
| `counterfactual` | DEMOTE | "What-if" branch observability; operator-only. |
| `critiques` | **DELETE** | Critiques mirror — no founder-facing workflow lives here; adversarial + responses + peer-review cover the actual workflow. |
| `dashboard` | KEEP | Operator home (principles rail, signals, drift). |
| `deals` | DEMOTE | Deal tracking — portfolio is the canonical surface. Keep as operator-only metadata view; not in primary nav. |
| `decay` | DEMOTE | Decay observability; flagged on dashboard, detail in `/ops/`. |
| `dialectic` | DEMOTE | Session logging surface — operator-only audit. Public detail page (handled in §A) DELETE; authed detail keeps. |
| `eval` | DEMOTE | Test/eval observability. |
| `explorer` | KEEP | Founder uses the 2D-embedding canvas for active discovery. |
| `extractor` | DEMOTE | Pipeline-stage observability. |
| `forecasts` | KEEP | Operator manages prediction-market portfolio here. |
| `founder-currents` | KEEP | Curated-opinions surface (X / feeds). |
| `founders` | DEMOTE | Multi-founder roster observability; the firm is currently single-operator. |
| `knowledge` | KEEP | Multi-tab knowledge browser (Conclusions / Principles / Cases / Explorer / Library / Transcripts). Founder entry into the corpus. |
| `knowledge-graph` | KEEP-as-operator | Sub-route at `knowledge-graph/operator`; keep, primary nav already routes to public graph. |
| `library` | KEEP | Org-wide upload inventory. |
| `literature` | DEMOTE | Paper catalog observability. |
| `memos` | KEEP | Memo compose / review / publish lifecycle. |
| `methodology-review-week` | DEMOTE | Weekly operator report. |
| `methods` | KEEP | Method evaluation surface (severity, reliability). |
| `open-questions` | DEMOTE | Future-work backlog observability. |
| `ops` | KEEP-as-operator | The canonical operator runbook; will absorb other demoted routes. |
| `oracle` | KEEP | Synthesis-with-provenance query surface. |
| `papers` | DEMOTE | Auto-paper review queue; operator-only. |
| `peer-review` | DEMOTE | Verdict triage; operator-only. |
| `portfolio` | KEEP | Unified capital-deployment surface (markets + equities). |
| `portfolio-agents` | DEMOTE | Agent observability — subsume into `/portfolio`. |
| `post-mortem` | DEMOTE | Decision-autopsy logs; operator-only. |
| `principles` | KEEP | Principles triage queue + detail (the firm's spine). |
| `provenance` | DEMOTE | Source-lineage observability. |
| `publication` | KEEP | Publishing review queue (the gate to public). |
| `q` | DEMOTE | Only sub-route is `q/review/page.tsx` (operator review queue). Move under `/ops/`. |
| `reading-queue` | KEEP | Founder reading list. |
| `research` | DEMOTE | Research observability — derived from `/papers`. |
| `responses` | KEEP | Inbound feedback / objections. |
| `rigor-gate` | KEEP | Quality gate before firm-tier promotion. |
| `scoreboard` | DEMOTE | Forecast-accuracy leaderboard observability. |
| `sessions` | DEMOTE | Session-log observability. |
| `social` | DEMOTE | Social/public-profile aggregation observability. |
| `source-triage` | DEMOTE | Citation-verdict triage. Operator-only. |
| `subscribers` | DEMOTE | Subscriber list observability. |
| `transcripts` | KEEP | Transcript catalog (founder-facing). |
| `upload` | KEEP | Core ingest surface. |
| `voices` | DEMOTE | Voice-model / speaker metadata. |

**Authed totals:** ~54 routes audited. 24 KEEP, 1 DELETE (`critiques`), 29 DEMOTE.

---

## C. API routes (`src/app/api/*` and `src/app/(authed)/api/*`)

The vast majority (>90 endpoints) are load-bearing for either the public reader surface, the founder workflow, the auth surface, or the calibration / publication pipelines. Detailed table lives in the survey artifacts; only the verdicts of interest are recorded here.

### Verdicts of interest (deviations from KEEP)

| Route | Verdict | Justification |
|---|---|---|
| `/api/conclusion-deletion-requests/*` (PUBLIC `src/app/api/` — GET, POST, PATCH `[id]`) | **DEMOTE** | Grep across `src/` shows zero HTTP callers; the workflow that exists (library-page server action) uses Prisma directly, not this endpoint. Yet the model + feature are live, so deleting the HTTP surface is borderline. Move from `src/app/api/conclusion-deletion-requests/*` to `src/app/(authed)/api/conclusion-deletion-requests/*` so the endpoint is auth-gated. Reversible by moving the file back. |
| `/api/dashboard-dismissals` | KEEP | Grep shows real callers (`dashboard/actions.ts`, `dashboardDismissalActions.test.ts`, schema). Live route. |
| `/api/contradictions/[id]` | KEEP | Manual-resolve / dismiss removed (per prompt 08); endpoint correctly 404s on legacy actions. Load-bearing for source-driven lifecycle. |

### Recommended API deletes (final)

None. The single near-miss (`/api/conclusion-deletion-requests`) is DEMOTEd rather than DELETEd because the underlying workflow model is still live.

---

## D. Prisma models (`theseus-codex/prisma/schema.prisma`)

110+ models total. Almost all are load-bearing for the belief→algorithm→forecast→calibration→publication pipeline. The full table lives in survey artifacts; only the non-KEEP rows are reproduced here.

### Verdicts of interest

| Model | Verdict | Justification |
|---|---|---|
| `DealPrincipleAlignment` | **DELETE** | Grep across the whole repo: only schema definition + migration files reference it. No Python, no TS reads or writes it. Sidecar to a feature (`Deal`) that itself is being DEMOTEd. |
| `SubscriberBounce` | **DELETE** | Only reference outside schema is a comment in `noosphere/scripts/run_first_digest.sh`. Email-bounce telemetry is not load-bearing for Philosopher-in-a-Box. |
| `ContradictionDispute`, `ContradictionLifecycle` | DEMOTE | Audit trail for contradictions. Kept for operator observability; not in public API. Mark `@internal`. |
| `ResolutionOverride`, `ResolutionMismatch`, `ResolutionRevision` | DEMOTE | Resolution-repair audit. Operator-only. |
| `GraphEdgeReasoning` | DEMOTE | Edge-reasoning cache; never exposed in API. |
| `PrincipleClusterCentroid`, `PrincipleConvictionUpdateQueue`, `ContradictionTestTask`, `ClusterReindexProposal` | DEMOTE | Internal ML / scheduler artifacts. |

### Recommended Prisma deletes (final)

- `DealPrincipleAlignment` — code-only deprecation, deprecation migration written. Data drop scheduled for Round 21.
- `SubscriberBounce` — same.

### Recommended Prisma demotes (final)

Eight models above. The demotion is mechanical: add `/// @demoted: operator-only` annotation to each model in `schema.prisma` and strip any TS-side query helpers from the public API surface (kept in operator-only helpers).

---

## E. Noosphere modules

The deprecated-coherence cluster is the major target.

| Module | Verdict | Justification |
|---|---|---|
| `noosphere/coherence/argumentation.py` | **DELETE** | Layer 2 (Dung-style voting). Only callers are the legacy `aggregator.py`, the legacy `six_layer_coherence` method, and the deprecation `__init__.py`. The contradiction-geometry engine (the replacement) does not import it. |
| `noosphere/coherence/information.py` | **DELETE** | Layer 5 (compression). Same caller pattern. The "don't make sense" heuristic per prompt-06 notes. |
| `noosphere/coherence/probabilistic.py` | **DELETE** | Layer 3 (Kolmogorov). Same caller pattern. |
| `noosphere/coherence/judge.py` | **DELETE** | Layer 6 (LLM rationality judge). Same caller pattern. |
| `noosphere/coherence/engine.py` | DEMOTE | The 6-layer orchestrator. Still referenced by tests + scheduler; will become a legacy shim that raises `Deprecated` for new callers, kept only for regression. |
| `noosphere/coherence/__init__.py` | DEMOTE | Compat re-exports; trim to expose only the surviving symbols (`engine`, `geometry.hoyer_sparsity`, `nli.StubNLIScorer`). |
| `noosphere/coherence/geometry.py` | KEEP | `hoyer_sparsity()` is a live import from the new engine. Module survives as a utility. |
| `noosphere/coherence/nli.py` | KEEP | `StubNLIScorer` + the DeBERTa encoder are still referenced by the new engine. |
| `noosphere/coherence/aggregator.py` | DEMOTE | Wrapper around the six layers. Becomes a legacy-only path used solely by the `six_layer_coherence` legacy method (kept for regression-only). |
| `noosphere/methods/_legacy/six_layer_coherence.py` | DEMOTE | Already in `_legacy/`. Mark `@deprecated`, keep for regression suite only. |
| `noosphere/coherence/contradiction_engine.py` | KEEP | The replacement engine — load-bearing. |
| `noosphere/coherence/contradiction_*.py` (scheduler, direction, cluster_index, auto_resolver, locality, lifecycle, recalibration, horizon_calibration, calibration, scheduler, cache, metrics) | KEEP | All load-bearing for the new coherence pipeline. |
| `noosphere/models.py`, `noosphere/cli_commands/methods.py`, `noosphere/docgen/seasonal_review.py`, `noosphere/methods/_registry.py`, `noosphere/methods/retirement.py`, `noosphere/peer_review/reviewers/methodological.py` | KEEP | Marked "deprecated" in the surface scan was a false-positive — these are active. |

### Recommended noosphere deletes (final)

- `noosphere/coherence/argumentation.py` (+ tests)
- `noosphere/coherence/information.py` (+ tests)
- `noosphere/coherence/probabilistic.py` (+ tests)
- `noosphere/coherence/judge.py` (+ tests)

Before delete: confirm `noosphere/coherence/__init__.py` re-exports are removed and `aggregator.py` either drops the imports or is itself moved into `_legacy/`.

---

## Summary table

| Category | Audited | KEEP | DEMOTE | DELETE |
|---|---:|---:|---:|---:|
| Public routes | 24 | 21 | 1 (`/dialectic` → authed) | 2 (`/critiques`, `/revisions`) |
| Authed routes | 54 | 24 | 29 | 1 (`critiques`) |
| API routes | ~95 | ~94 | 1 tree (`conclusion-deletion-requests` → authed) | 0 |
| Prisma models | ~110 | ~100 | 8 | 2 (`DealPrincipleAlignment`, `SubscriberBounce`) |
| Noosphere coherence modules | ~22 | 12 | 6 | 4 (`argumentation`, `information`, `probabilistic`, `judge`) |
| **Totals** | **~305** | **~251** | **~45** | **~9** |

---

## Full DELETE list (single source of truth for the Plan doc)

1. **Public:** `theseus-codex/src/app/critiques/page.tsx` (+ subroutes if any).
2. **Public:** `theseus-codex/src/app/revisions/page.tsx` (index only; `/revisions/[event-id]` keeps).
3. **Authed:** `theseus-codex/src/app/(authed)/critiques/*`.
4. **Prisma:** `DealPrincipleAlignment` model (deprecation migration, 90-day data hold).
5. **Prisma:** `SubscriberBounce` model (deprecation migration, 90-day data hold).
6. **Noosphere:** `noosphere/noosphere/coherence/argumentation.py` (no test file).
7. **Noosphere:** `noosphere/noosphere/coherence/information.py` (no test file).
8. **Noosphere:** `noosphere/noosphere/coherence/probabilistic.py` (no test file).
9. **Noosphere:** `noosphere/noosphere/coherence/judge.py` — also strip the import inside `noosphere/tests/test_coherence_eval.py:164`.

## Full DEMOTE list

### Public surface
- `theseus-codex/src/app/dialectic/sessions/[id]` — move under `(authed)/`.

### Authed surface (move under `(authed)/ops/*`, remove from primary nav, add path redirect)
adversarial, algorithms (operator + queue), cascade, counterfactual, decay, deals, dialectic, eval, extractor, founders, knowledge-graph (operator), literature, methodology-review-week, open-questions, papers, peer-review, portfolio-agents (into `/portfolio`), post-mortem, provenance, q, research, scoreboard, sessions, social, source-triage, subscribers, voices.

### Prisma (annotate `/// @demoted: operator-only`; strip from public API helpers)
ContradictionDispute, ContradictionLifecycle, ResolutionOverride, ResolutionMismatch, ResolutionRevision, GraphEdgeReasoning, PrincipleClusterCentroid, PrincipleConvictionUpdateQueue, ContradictionTestTask, ClusterReindexProposal.

### Noosphere (mark `@deprecated`; legacy-only callers; raise `DeprecationWarning` on import)
- `noosphere/coherence/__init__.py` (trim re-exports)
- `noosphere/coherence/engine.py`
- `noosphere/coherence/aggregator.py`
- `noosphere/methods/_legacy/six_layer_coherence.py`

---

## Reversibility note

Every DELETE is reversible from git history. The deprecation migrations on Prisma models keep the underlying tables intact for ≥90 days; only the code surface goes away. Detailed restoration steps live in the Plan doc.

---

## Founder sign-off needed

The execution step (C) does not run until the founder signs off on this audit. If any DELETE in this document should be a DEMOTE, or any DEMOTE should be a KEEP, mark it on this doc and the Plan will be revised before any code is touched.
