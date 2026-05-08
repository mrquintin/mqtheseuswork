# Round 16 — Public-Surface UX Cleanup + Publication Cadence

Active batch created 2026-05-07 from a transcript covering: nav home /
"Founder Portal" rename / Responses removal; Articles typography
(de-uppercase titles, justify with hyphenation) and clutter trim;
firm-side sources compaction; Currents citation popover redesign;
Currents/Forecasts theme alignment + clutter removal; response-email
pipeline; weekly publication cadence + content-quality gating.

The previous Round 15 (Currents inversion + coherence at scale) batch is
archived under `archive_round15_currents_and_coherence_implemented/` —
the audit script reports every declared SCOPE file exists for all nine
of those prompts, and the founder's transcript on 2026-05-07 confirms
the X-card cosmetic fix landed ("I think you fixed it").

The active runnable batch is exactly the top-level numbered prompt set:

1. `01_public_nav_home_founder_portal_drop_responses.txt` — Home item;
   Dashboard → Founder Portal; remove Responses from nav; PublicHeader
   on Currents/Forecasts.
2. `02_remove_responses_page_inline_response_form.txt` — delete
   `/responses`, rehome the form at the TOP of `/post/[slug]` and
   `/c/[slug]`.
3. `03_response_email_pipeline.txt` — wire submit → email to founder
   alpha (Resend / SMTP / no-op fallback); founder-side inbox surface.
4. `04_article_typography_layout_cleanup.txt` — drop the Cinzel caps
   font; justify body with hyphenation; remove four clutter sections
   from the conclusion page.
5. `05_article_firm_sources_compact.txt` — compact "Sources" list with
   conclusion text per row; show source link ONLY when public
   visibility.
6. `06_currents_citation_popover.txt` — inline `[opinion]` /
   `[firm conclusion]` tokens with click-to-popover; visibility-gated
   public link.
7. `07_currents_chrome_cleanup.txt` — site theme on Currents; remove
   PublishToToolbar, SourceDrawer, AuditTrail; back link.
8. `08_forecasts_site_theme_and_home.txt` — same treatment for
   Forecasts.
9. `09_publication_cadence_weekly_quality.txt` — weekly cap (was 4/day);
   quality gate; "newest opinions" weighting; 70-char title rule.
10. `10_verification_and_regression.txt` — single regression pass +
    report.

`run_prompts.sh` discovers only top-level
`coding_prompts/[0-9][0-9]_*.txt` files. It does not descend into
`_paused/`, `archive_round*/`, or any other subdirectory.

## Run

```bash
cd /Users/michaelquintin/Desktop/Theseus
./run_prompts.sh
```

Useful filters:

```bash
./run_prompts.sh --dry-run
./run_prompts.sh --from 4
./run_prompts.sh --to 6
./run_prompts.sh --from 2 --to 6
./run_prompts.sh --only 06
./run_prompts.sh --model gpt-5.3-codex
./run_prompts.sh --continue
```

The runner uses the OpenAI Codex CLI login/subscription path
(`codex exec`), NOT an OpenAI API key. It scrubs `OPENAI_API_KEY`,
`OPENAI_AUTH_TOKEN`, `OPENAI_BASE_URL`, `OPENAI_ORG_ID`, and
`OPENAI_PROJECT` before each Codex invocation so a Cursor terminal with
stale API-key vars still uses the Codex CLI login path. Every Codex
session streams to the terminal and is captured at
`.codex_runs/<timestamp>_<prompt>.log`.

Each prompt instructs Codex to inspect current code and tests first,
verify already-landed work, and make only necessary repair edits.
Reruns are intended to be idempotent.

## Audit

```bash
python3 coding_prompts/_audit_implementation.py
```

Inter-prompt dependencies (worth knowing if you re-order):

- 02 depends on 01 (PublicHeader change must land before the nav loses
  its Responses link, or the redirect would briefly break the nav).
- 03 depends on 02 (form must already POST to the existing endpoint;
  this prompt only side-channels the email).
- 04 + 05 are independent of each other but both touch
  `ConclusionView.tsx`; running 04 before 05 reduces merge conflicts.
- 06 depends on 04 + 05 (the citation popover replaces the bottom
  citation strip that 04 already trimmed).
- 07 depends on 01 (PublicHeader on Currents) and 06 (the inline
  citation tokens replace the footer strip the cleanup also removes).
- 08 depends on 01 + 07 (the same theme-alignment idiom as Currents).
- 09 is independent of the UI prompts.
- 10 depends on 01–09.

## Triage notes from the audit run on 2026-05-07

The Round 15 prompts were re-audited and found IMPLEMENTED across the
board. They were moved to
`archive_round15_currents_and_coherence_implemented/`.

The remaining NOT_IMPLEMENTED entries surfaced by the audit live in
deeper archive folders (round 9 + round 10 design briefs whose output
docs exist at slightly different paths). They are confirmed false
negatives and stay archived.

## Archives

- `archive_round15_currents_and_coherence_implemented/` — Currents
  inversion, X significance metrics, noosphere coherence at scale,
  production migration runner.
- `archive_round14_methodology_implemented/` — methodology extraction.
- `archive_round13_conversation_geometry_implemented/` — conversation
  geometry.
