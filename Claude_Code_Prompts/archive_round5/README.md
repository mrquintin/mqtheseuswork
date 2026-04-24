# Bug-Fix and Product-Refinement Prompts (Round 5)

25 Claude Code prompts that address bugs, design flaws, and product gaps in the Theseus Codex's review and conclusions system, with targeted changes to Noosphere where needed.

## Prompt index

| # | Name | What it fixes | Touches |
|---|------|--------------|---------|
| 01 | `tenant_scoping_raw_queries` | Raw SQL queries in round3.ts lack organizationId filter — any user sees any org's data | Codex |
| 02 | `conclusion_detail_auth_scope` | `/conclusions/[id]` has no tenant check — any authed user can view any org's conclusions | Codex |
| 03 | `server_action_self_fetch` | Server actions in peer-review and decay pages HTTP-fetch their own server (breaks auth, fragile) | Codex |
| 04 | `review_queue_show_claim_text` | Coherence review queue shows truncated UUIDs instead of actual claim text | Codex |
| 05 | `review_queue_resolution_notes` | No text field for human reasoning when resolving review items — verdicts capture no rationale | Codex |
| 06 | `review_queue_optimistic_ui` | `window.location.reload()` after each verdict — destroys scroll position and context | Codex |
| 07 | `overview_tab_resolve_ids` | Overview tab shows opaque counts for principles/evidence/dissent — never shows actual text | Codex, Noosphere |
| 08 | `overview_tab_source_uploads` | Overview tab has no link to the source uploads that produced the conclusion | Codex |
| 09 | `missing_table_diagnostics` | Provenance/cascade/peer-review/decay tabs silently show "no records" when tables don't exist | Codex |
| 10 | `cascade_tab_visual_tree` | Cascade tab uses raw indentation with no connecting lines — deep trees are unreadable | Codex |
| 11 | `provenance_method_links` | Provenance tab shows raw extraction method names with no link to the method registry | Codex |
| 12 | `conclusion_detail_actions` | Detail page is read-only — no way to retract, challenge, or queue for publication from it | Codex |
| 13 | `conclusions_list_search` | No free-text search on conclusions — only tier filters and one hardcoded topic filter | Codex |
| 14 | `conclusions_list_pagination` | Hard-coded `take: 80` with no pagination controls | Codex |
| 15 | `replay_mode_links` | Replay-mode conclusions render without `<Link>` wrappers — items are not clickable | Codex |
| 16 | `confidence_display_context` | Bare "Confidence 73%" with no explanation of scale, computation, tier thresholds, or distribution | Codex |
| 17 | `peer_review_verdict_vocabulary` | Two review systems (coherence: cohere/contradict/unresolved; peer: endorse/challenge/abstain) with no explanation | Codex |
| 18 | `shared_verdict_color_util` | Identical `verdictColor()` function duplicated across peer-review-tab.tsx and peer-review page | Codex |
| 19 | `export_blob_urls` | CSV/JSON exports use `data:` URIs via encodeURIComponent — crashes browser on large datasets | Codex |
| 20 | `decay_alerts_dashboard` | No proactive alerts for decaying/expired conclusions — users must manually check the dashboard | Codex |
| 21 | `related_conclusions` | No way to see conclusions that share principles, evidence, or source uploads with the current one | Codex |
| 22 | `peer_review_findings_detail` | Peer review tab shows reviewer name + verdict + commentary but not the structured findings | Codex, Noosphere |
| 23 | `review_queue_batch_ops` | No batch operations on the review queue — each item must be resolved one at a time | Codex |
| 24 | `conclusion_history_timeline` | No way to see the evolution of a conclusion over time (confidence changes, reviews, decays) | Codex |
| 25 | `noosphere_review_sync_audit` | Noosphere sync failures on review resolution are warned but never retried or surfaced in audit log | Codex, Noosphere |

## Wave structure

Prompts within a wave touch disjoint file sets and can run in parallel. Waves must run sequentially.

- **Wave 1** (01–03): Security and correctness — tenant scoping, auth, server-action rewrites
- **Wave 2** (04–06): Review queue UX — claim text, resolution notes, optimistic updates
- **Wave 3** (07–11): Tab content quality — resolved IDs, source links, diagnostics, tree visuals, method links
- **Wave 4** (12–16): Conclusions list and detail — actions, search, pagination, replay links, confidence context
- **Wave 5** (17–21): Polish and infrastructure — vocabulary clarity, shared utils, exports, alerts, related conclusions
- **Wave 6** (22–25): Advanced features — findings detail, batch ops, history timeline, sync audit

## Running

Use the `run_prompts.sh` script at the repo root:

```bash
./run_prompts.sh                  # run all 25 prompts sequentially
./run_prompts.sh --from 7         # start at prompt 07
./run_prompts.sh --only 04        # run only prompt 04
./run_prompts.sh --dry-run        # show plan without executing
./run_prompts.sh --continue       # don't halt on failure
```

## Archive

Previous rounds are in `archive_round3/` (26 prompts) and `archive_round4/` (8 prompts).
