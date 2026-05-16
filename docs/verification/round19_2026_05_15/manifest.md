# Round 19 — deliverable manifest

Operator: prompt 18 (`coding_prompts/18_round19_verification.txt`).
Run: 2026-05-16.

Existence + non-trivial-content check across every SCOPE entry in
prompts 01–17. Glob patterns expanded against the working tree.
"OK" means file exists and has > 32 bytes (or > 100 bytes for
migration `.sql` / `.py` files), `MISSING` means the SCOPE path is
absent, `EMPTY` means present but stub-sized, `STILL_PRESENT`
applies to `DELETE` actions that did not happen.

## Per-prompt roll-up

| Prompt | SCOPE rows | OK | Gaps |
|---|---:|---:|---|
| P01 algorithm data model           | 11 | 11 | — |
| P02 algorithm extraction           | 10 | 10 | — |
| P03 algorithm runtime              |  9 |  9 | — |
| P04 algorithm visibility surface   | 18 | 18 | — |
| P05 algorithm calibration          |  7 |  7 | — |
| P06 contradiction-engine           |  8 |  8 | — |
| P07 cluster pre-filter             |  7 |  7 | — |
| P08 source-driven resolution       |  9 |  9 | — |
| P09 provenance demarcation         | 11 | 11 | — |
| P10 synthesizer engine             |  9 |  9 | — |
| P11 investment-memo format         | 14 | 14 | — |
| P12 portfolio-agent interface      | 14 | 13 | `theseus-codex/src/app/portfolio/page.tsx` MODIFY — implementer modified `(authed)/portfolio/page.tsx` instead (same SCOPE drift pattern Round 18 P63 had). |
| P13 knowledge-graph view           | 16 | 16 | — |
| P14 dialectic live recording       | 15 | 15 | — |
| P15 polymorphic bet abstraction    | 15 | 15 | — |
| P16 deletion pass                  |  4 |  3 | `theseus-codex/__tests__/round19_deletion_invariants.test.ts` MISSING. Deletion Audit + Plan + README modification present. |
| P17 identity + pitch deck          | 12 | 12 | `deck.pdf` is present and built. |

**Totals**: 189 SCOPE rows, 187 OK, 2 SCOPE drifts.

## Notable

- `theseus-codex/src/app/(authed)/contradictions/[id]/resolve/page.tsx`
  is gone (P08 `DELETE` honoured).
- Every prompt-numbered Alembic revision (`015_contradiction_engine`
  through `024_bet_polymorphism`) and its Prisma migration twin is
  present; `alembic upgrade head` against a fresh SQLite DB runs
  cleanly through `024` (see `alembic.log`).
- `docs/pitch/2026_philosopher_in_a_box/deck.pdf` is present and
  rebuilt by `build_deck.sh` (live snapshot stub feeds
  `slide11_data.tex`).
- `docs/memos/_template.tex` + `build_memo_pdf.sh` present;
  `.gitkeep` placeholder present.

## Two SCOPE drifts to file for Round 20

1. **`portfolio/page.tsx` path drift (P12).** Implementer used
   `theseus-codex/src/app/(authed)/portfolio/page.tsx` (authed
   route) rather than the SCOPE-listed unauthed `portfolio/page.tsx`.
   Same drift as Round 18 P63. Either the SCOPE is wrong (portfolio
   should always be authed) or the unauthed surface is missing.
2. **`round19_deletion_invariants.test.ts` missing (P16).** The
   Deletion Audit + Plan docs are committed, but the test that
   would have asserted "every DELETE'd path returns 410 or is
   gone" was never written. Backlog for Round 20.

Both are flagged in `SUMMARY.md` under "Open questions".
