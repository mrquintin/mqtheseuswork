# Round-18 empirical artifact spot-check

Per-prompt resolution of declared SCOPE artifacts. 
For each artifact: file present? non-empty? numeric content?
placeholders flagged?

## Prompt 13 — QH benchmark v1 first run

- `benchmarks/quintin_hypothesis/v1/results/20260514T052854Z/results.json` — 19,328 bytes
- `benchmarks/quintin_hypothesis/v1/results/20260514T052854Z/envelope.json` — 2,337 bytes
- `benchmarks/quintin_hypothesis/v1/results/20260514T052854Z/analysis.md` — 6,771 bytes
- `docs/research/QH_Benchmark_v1_Results.tex` — 5,569 bytes
- `docs/research/QH_Benchmark_v1_Results.pdf` — 221,130 bytes (binary)
- `noosphere/scripts/run_qh_full.sh` — 12,592 bytes
- `noosphere/tests/test_qh_full_run_integration.py` — 16,643 bytes
- `theseus-codex/src/app/methodology/benchmark/qh/page.tsx` — 37,284 bytes

**Prompt 13 verdict: REAL** (8 artifact(s) resolved)

## Prompt 14 — Cross-model geometry study

- `benchmarks/quintin_hypothesis/v1/results/cross_model/20260514T060554Z/results.parquet` — 420,244 bytes (binary)
- `benchmarks/quintin_hypothesis/v1/results/cross_model/20260514T060554Z/envelope.json` — 4,497 bytes
- `benchmarks/quintin_hypothesis/v1/results/cross_model/20260514T060554Z/analysis.md` — 7,208 bytes
- `docs/research/Cross_Model_Geometry_Study.tex` — 6,787 bytes
- `docs/research/Cross_Model_Geometry_Study.pdf` — 312,639 bytes (binary)
- `docs/research/internal/Cross_Model_Findings_Memo.md` — 7,962 bytes
- `theseus-codex/src/app/methodology/benchmark/qh/cross-model/page.tsx` — 34,331 bytes
- `noosphere/scripts/run_cross_model_full.sh` — 29,463 bytes

**Prompt 14 verdict: REAL** (8 artifact(s) resolved)

## Prompt 15 — Householder ablation

- `benchmarks/quintin_hypothesis/v1/results/ablations/20260514T062948Z/results.json` — 2,845,656 bytes
- `benchmarks/quintin_hypothesis/v1/results/ablations/20260514T062948Z/envelope.json` — 1,681 bytes
- `docs/research/Householder_Ablation.tex` — 11,169 bytes
- `docs/research/Householder_Ablation.pdf` — 261,455 bytes (binary)
- `docs/research/internal/Ablation_Decisions.md` — 4,671 bytes
- `theseus-codex/src/app/methodology/contradiction_geometry/page.tsx` — 11,304 bytes

**Prompt 15 verdict: REAL** (6 artifact(s) resolved)

## Prompt 16 — Red-team tournament v1

- `benchmarks/redteam/v1/results/20260514T063830Z/results.json` — 14,895 bytes
- `benchmarks/redteam/v1/results/20260514T063830Z/envelope.json` — 907 bytes
- `benchmarks/redteam/v1/results/20260514T063830Z/leaderboard.csv` — 1,272 bytes
- `docs/research/internal/Redteam_Tournament_20260514T063830Z.md` — 11,945 bytes
- `theseus-codex/src/app/methodology/redteam/page.tsx` — 21,073 bytes
- `noosphere/scripts/run_redteam_tournament_v1.sh` — 23,856 bytes

**Prompt 16 verdict: REAL** (6 artifact(s) resolved)

## Prompt 17 — Principle distillation pass

- `noosphere/scripts/run_principle_distillation.sh` — 26,148 bytes
- `docs/research/internal/Principle_Distillation_20260514T120000Z.md` — 7,016 bytes
- `theseus-codex/src/app/(authed)/principles/queue/page.tsx` — 4,036 bytes
- `noosphere/noosphere/distillation/principle_distillation.py` — 46,278 bytes
- `noosphere/tests/test_principle_distillation_integration.py` — 22,940 bytes

**Prompt 17 verdict: REAL** (5 artifact(s) resolved)

## Prompt 18 — Forecast resolution backfill

- `docs/runs/resolution_backfill_20260514T172931Z_dryrun.md` — 1,423 bytes
- `docs/runs/resolution_backfill_20260514T172931Z.md` — 1,450 bytes
- `docs/runs/resolution_backfill_20260514T172931Z_dryrun.md` — 1,423 bytes
- `noosphere/scripts/run_resolution_backfill.sh` — 37,508 bytes
- `noosphere/tests/test_resolution_backfill_integration.py` — 24,524 bytes

**Prompt 18 verdict: REAL** (5 artifact(s) resolved)

## Prompt 19 — Self-critique pass

- `noosphere/scripts/run_self_critique_pass.sh` — 49,152 bytes
- `docs/runs/self_critique_20260514T174516Z.md` — 2,396 bytes
- `docs/runs/self_critique_20260514T174516Z/` — directory with 1 file(s)
- `docs/runs/self_critique_20260514T174516Z.md` — 2,396 bytes
- `noosphere/tests/test_self_critique_integration.py` — 16,467 bytes

**Prompt 19 verdict: REAL** (5 artifact(s) resolved)

## Prompt 20 — First auto paper

- `noosphere/scripts/run_first_auto_paper.sh` — 35,112 bytes
- `docs/research/auto/adversarial-audit-2a74eb9b-adversarial-probing-of-hidden-assumptions-a-firm-cluster/paper.tex` — 5,888 bytes
- `docs/research/auto/bayesian-update-12a26716-calibrated-narrowing-under-uncertainty-a-firm-cluster/paper.tex` — 6,301 bytes
- `docs/research/auto/representational-geometry-109123c7-geometric-contradiction-detection-a-firm-cluster/paper.tex` — 5,302 bytes
- `docs/research/auto/adversarial-audit-2a74eb9b-adversarial-probing-of-hidden-assumptions-a-firm-cluster/paper.pdf` — 176,090 bytes (binary)
- `docs/research/auto/bayesian-update-12a26716-calibrated-narrowing-under-uncertainty-a-firm-cluster/paper.pdf` — 178,323 bytes (binary)
- `docs/research/auto/representational-geometry-109123c7-geometric-contradiction-detection-a-firm-cluster/paper.pdf` — 178,129 bytes (binary)
- `docs/research/internal/Auto_Paper_Candidates_20260514T120000Z.md` — 4,924 bytes
- `noosphere/tests/test_auto_paper_integration.py` — 26,735 bytes

**Prompt 20 verdict: REAL** (9 artifact(s) resolved)
