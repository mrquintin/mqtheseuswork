# Theseus preset · VC firm

Theseus's `vc_firm` preset is an opinionated configuration for a
venture-capital firm whose intellectual capital is its partners'
writing, podcasts, and interview transcripts. It is the template plus
opinionated module flags plus a `/deals` workflow.

The preset is **opinionated, not locked**. Every module flag below
can be flipped back on later by editing `.env.live` or the org
settings. Public-equities and prediction-market trading remain OFF
unless the tenant explicitly toggles them and completes the operator
rehearsal.

## What you get

| Module       | Default | Why |
|--------------|---------|-----|
| `principles` | on      | The load-bearing module. Distilled from partner writing. |
| `oracle`     | on      | Partners ask questions of the firm's own corpus daily. |
| `currents`   | on      | Grounded opinion on current events. |
| `deals`      | on      | The daily-driver surface for this preset. |
| `forecasts`  | **off** | VCs typically do not care about Polymarket. |
| `equities`   | **off** | VCs invest privately; public-equity signal is rarely on the critical path. |

`/deals` is the primary surface. `/principles` and `/oracle` are
adjacent. `/forecasts` and `/equities` are hidden until re-enabled.

The principle extractor preferentially tags claims against:

    market_size, founder_quality, timing, moats, unit_economics,
    competition, team, regulatory

These are hints, not a closed set — the extractor will emit new
domains when the corpus warrants.

## Bootstrap

    ./theseus-template/scripts/bootstrap.sh --preset vc_firm

The wizard:

1. Asks for the firm's name, slug, admin email, DB URL, and LLM
   provider keys (same as the base template).
2. Asks for each founding partner's name. For each partner, creates
   `tenant_data/<slug>/founders/<partner-slug>/` with `essays/` and
   `transcripts/` subfolders and a README explaining what to drop
   there.
3. Materialises the preset's `seed_artifacts`: `founders/`,
   `firm_memos/`, `partner_meeting_notes/` directories under the
   tenant data dir, each with a README.
4. Pauses so the operator can drop the first batch of materials, then
   runs the principle extractor (prompt 56) over the uploads.
5. Runs the principle distillation pass (prompt 17 + prompt 56).
6. Surfaces the principle queue at `/principles/queue` for triage.

## Intended workflow

> Drop your partners' writing in `founders/`. Wait for principle
> distillation. Triage the queue. Create a deal. Watch the
> principle-alignment table populate. Draft a memo. Hold the meeting.

The cycle in detail:

1. **Drop partner materials.** Essays, podcast transcripts,
   interview transcripts — anything that records the partner's
   beliefs. Markdown, PDF, plain text, and `.srt` are all accepted.
   Memos and meeting notes go in `firm_memos/` and
   `partner_meeting_notes/`.
2. **Wait for principle distillation.** The extractor emits one or
   more candidate claims per artifact; the distillation pass
   clusters claims across the corpus and proposes principles only
   when the convergence is cross-domain (a single high-centrality
   conclusion is not enough — see
   `noosphere/distillation/principle_distillation.py`).
3. **Triage the queue.** `/principles/queue` shows the firm's draft
   principles ordered by conviction. Accept (with optional edits),
   reject (with reason), or merge into an existing principle.
   Triage is the only step that requires partner attention every
   week.
4. **Create a deal.** From `/deals`, fill in name, stage, sector,
   geography, and upload source documents (pitch deck, founder bio,
   market reports, your own notes).
5. **Watch the alignment table populate.** The alignment runner
   selects principles whose declared domains intersect the deal's
   sector + stage, then emits a `MATCH | CONFLICT | UNCLEAR`
   verdict with citations per principle. Re-runs are idempotent:
   the table upserts on `(deal_id, principle_id)`.
6. **Sketch a memo.** The "Sketch a memo" action drafts an
   investment-committee memo from the alignment table, grouping
   principles into _in support_, _in tension_, and _insufficient
   signal_. The draft is labelled DRAFT and is **never**
   auto-promoted — the partner reads, edits, signs.
7. **Hold the meeting.** Append partner-meeting notes to the deal.
   Notes cite specific principles by id; the UI links each citation
   to the principle detail page so subsequent reviewers can read the
   citation trail.

## What the agent does and does not do

The agent surfaces which firm principles apply to a deal and what the
citation trail looks like. The agent **does not**:

* Decide whether to invest.
* Make a positive recommendation.
* Auto-promote any memo body to "final".
* Trade in any market on behalf of the firm.

These remain partner decisions. The eight-gate safety contract from
the base template still applies; the VC preset only adds a new
read-write surface, not new autonomous actions.

## Flipping module flags later

To re-enable forecasts or equities once the operator rehearsal in
`docs/operator/SCHEDULER_OPS.md` is complete, set the corresponding
flag in `.env.live`:

    FORECASTS_MODULE_ENABLED=true
    EQUITIES_MODULE_ENABLED=true

and restart the codex + scheduler. The preset's other defaults are
similarly per-tenant config — the preset writes them once at
bootstrap, it does not enforce them at runtime.

## Files

* `theseus-template/presets/vc_firm.yml` — preset descriptor.
* `theseus-template/presets/schema/preset.schema.json` — validator.
* `theseus-template/scripts/bootstrap.sh` — wizard, with
  `--preset vc_firm` support.
* `theseus-codex/src/app/(authed)/deals/` — UI pages.
* `theseus-codex/src/components/deals/PrincipleAlignmentTable.tsx` —
  the load-bearing alignment surface.
* `theseus-codex/src/components/deals/MemoDrafter.tsx` — the DRAFT
  memo composer.
* `noosphere/noosphere/vc/principle_alignment.py` — the runner.
