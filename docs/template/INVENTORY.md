# Theseus Template Inventory

This file is the authoritative classification of every top-level path in
the Theseus source repository against the template-extraction contract
defined in `coding_prompts/68_theseus_template_extraction.txt`.

Classifications

- **CORE** — copied verbatim into `theseus-template/`. These are
  platform mechanisms with no firm-specific content.
- **FIRM** — stays in the source repo only. Founder's writing,
  the firm's principles, the firm's named research benchmarks
  (Quintin Hypothesis, Cross-Model Geometry, Cross-Domain Transfer,
  Householder Ablation), the firm's podcasts/talks, the firm's
  founders-only reading lists.
- **CONFIG** — copied through a token-substitution pass driven by
  `scripts/template/manifest.yml`. Replaces firm name, default LLM,
  notification sender, etc.
- **SEED** — shipped as an empty-shape fixture (Markdown headings
  with no body; SQL fixtures with one demo row). The new tenant fills
  it in.

The extraction script `scripts/build_template.sh` walks this
inventory deterministically. When a new path is added to the source
repo, append it here in the right bucket so the extraction stays
faithful.

## Top-level paths

| Path | Class | Notes |
| ---- | ----- | ----- |
| `.editorconfig` | CORE | |
| `.env` | FIRM | Real secrets. Never copied. |
| `.env.live` | FIRM | Symlink to live secrets. Never copied. |
| `.env.live.fake` | FIRM | Empty placeholder. Not needed in template. |
| `.env.live.template` | CONFIG | Token-substituted; ships as the blank scaffold the tenant fills in. |
| `.env.production.fake` | FIRM | Stripped. |
| `.env.staging.fake` | FIRM | Stripped. |
| `.git/` | FIRM | Source history. Never copied. The template gets its own `git init`. |
| `.github/` | CONFIG | Workflows are copied with firm-specific job names tokenised. The `qh_benchmark.yml` and `redteam_tournament.yml` workflows are FIRM and stripped. |
| `.gitignore` | CORE | |
| `.claude/` | FIRM | Local Claude Code config + transcript surface for this operator. |
| `.claude_code_runs/` | FIRM | Stripped (log directory). |
| `.codex_runs/` | FIRM | Stripped (log directory). |
| `.pytest_cache/` | FIRM | Stripped (cache). |
| `.ruff_cache/` | FIRM | Stripped (cache). |
| `.venv/`, `.venv-*/` | FIRM | Stripped (local virtualenvs). |
| `.vercel/` | FIRM | Stripped (deploy tokens). |
| `.vscode/` | FIRM | Local IDE settings. |
| `benchmarks/` | FIRM | All three subdirs (`quintin_hypothesis/`, `redteam/`, `transfer/`) are firm-named research benchmarks. Stripped. |
| `build_claude_code_prompts.py` | FIRM | Prompt-runner harness wired to this firm's coding rounds. |
| `coding_prompts/` | FIRM | Round-by-round work product for this codebase. Including `archive_round*/`, `ui_ux_round*/`, `_paused/`, all round logs, `README.md`, and `UI_CRITIQUE_*.md`. Stripped wholesale. |
| `config/` | CONFIG | Three YAML files (`defaults.yaml`, `development.yaml`, `production.yaml`). Token-substituted. |
| `current_events_api/` | CORE | The Currents service. Platform. |
| `deploy/` | CORE | Compose / Docker / Helm / observability / SQL bootstrap. Generic. |
| `dialectic/` | CORE | Dialectic worker process. Platform. |
| `docker-compose.dev.yml` | CONFIG | Token-substituted (`THESEUS_ORG_NAME`). |
| `docker-compose.yml` | CONFIG | Token-substituted. |
| `Dockerfile.api` | CORE | |
| `Dockerfile.scheduler` | CORE | |
| `docs/` | mixed — see [docs sub-table](#docs-subtable) | |
| `format_stream_claude.py` | CORE | Generic Claude Code stream formatter. |
| `format_stream_events.py` | CORE | Generic event formatter. |
| `FOUNDERS_READING_AND_RESEARCH.md` | FIRM | Founder-specific curriculum. |
| `ideologicalOntology/` | FIRM | Founder's writing / research investigations. |
| `Makefile` | CORE | |
| `METHODOLOGICAL_REORIENTATION.md` | FIRM | Founder narrative. |
| `node_modules/` | FIRM | Stripped (rebuilt by `npm install`). |
| `Non-coding material/` | FIRM | Founder-curated reference material. |
| `noosphere/` | mostly CORE — see [noosphere sub-table](#noosphere-subtable) | |
| `noosphere_data/` | SEED | Runtime ledger. Ships as an empty directory with a stub `noosphere_config.json`. |
| `ops/` | CORE | Operational scripts. |
| `packages/` | CORE | `shared-schemas/`, `theseus-api-types/` — generic. |
| `Podcast talks/` | FIRM | Founder's recordings. |
| `pyproject.toml` | CONFIG | Project metadata; firm name and authors tokenised. |
| `README.md` | CONFIG | Replaced wholesale by `theseus-template/README.md` (see prompt section E). |
| `reference/` | FIRM | Provenance archive of starting material / original prototypes. Already gitignored in source. |
| `replication/` | CORE | Replication harness. Generic framework. The `runs/` subdirectory is SEED (ships empty). |
| `requirements.txt` | CORE | |
| `researcher_api/` | CORE | Researcher API service. Platform. |
| `run_prompts_codex.sh` | FIRM | Firm-specific prompt runner. |
| `run_prompts.sh` | FIRM | Firm-specific prompt runner. |
| `scripts/` | mixed — see [scripts sub-table](#scripts-subtable) | |
| `SETUP_GITHUB.sh` | FIRM | Wired to this firm's GitHub org. |
| `sync.sh` | FIRM | Wired to this firm's remote. |
| `tests/` | CORE | Cross-cutting integration tests against the platform. |
| `THE_META_METHOD.md` | CORE | Conceptual framing. No firm-specific data; refers to capabilities generically. Ships with a one-line attribution swap. |
| `Theseus_Stack_Architectural_Guide.pdf` | FIRM | Generated PDF assembled from firm-specific tex sources. Not in the prompt-67 guide set. Stripped. |
| `theseus-codex/` | mostly CORE — see [theseus-codex sub-table](#theseus-codex-subtable) | |
| `theseus-public/` | mostly CORE — see [theseus-public sub-table](#theseus-public-subtable) | |
| `theseus.egg-info/` | FIRM | Build artifact. |
| `TODO.md` | FIRM | Founder's working notes. |
| `WAVE3_TODO_STORE_HELPER.md` | FIRM | Round-specific TODO. |

## docs/ subtable {#docs-subtable}

| Path | Class | Notes |
| ---- | ----- | ----- |
| `docs/api-methods/` | CORE | Generic API reference. |
| `docs/architecture/` | CORE | Generic architecture notes. |
| `docs/archive/` | FIRM | Historical drafts. |
| `docs/Auto_Processing_Setup.md` | CORE | |
| `docs/benchmarks/` | FIRM | `QH_Benchmark_Schema.md` is a firm-named benchmark. Stripped. |
| `docs/bugs/` | FIRM | Bug ledger from this firm's operation. |
| `docs/CI_CD_Setup.{pdf,tex,…}` | CORE | Generic CI/CD guide. |
| `docs/currents/` | CORE | Currents method reference. |
| `docs/design/` | CORE | Generic design notes. |
| `docs/Desktop_Packaging.{pdf,tex,…}` | CORE | Generic packaging guide. |
| `docs/Docker_Deployment.{pdf,tex,…}` | CORE | Generic. |
| `docs/editorial/` | FIRM | Firm's editorial decisions. |
| `docs/eval/` | CORE | Evaluation method docs. |
| `docs/external/` | FIRM | Firm's external-replicator outreach. |
| `docs/Founders_Questions.pdf` | FIRM | Founder-only material. |
| `docs/Founders_Reading_and_Research.pdf` | FIRM | Founder curriculum. |
| `docs/Geometry_of_Unresolution.pdf` | FIRM | Firm research paper. |
| `docs/guides/` | CORE | The prompt-67 user guides (PDF + tex). Explicitly carried over per the prompt: *"all generated PDFs except the guides from prompt 67 (which are general-purpose)"*. |
| `docs/interop/` | CORE | Generic interop docs. |
| `docs/Methodological_Reorientation.pdf` | FIRM | Generated from firm-narrative .md. |
| `docs/methods/` | CORE | The platform's method specifications (MQS, Bayesian Belief Layer, etc.). |
| `docs/Noosphere_Project_Status.pdf` | FIRM | Firm status report. |
| `docs/operations/` | CORE | Generic operations docs. |
| `docs/Operations_Manual.md` | CORE | |
| `docs/operator/` | CORE | Operator reference (Currents, scheduler ops, public surfacing). |
| `docs/peer_review/` | CORE | Peer-review method spec. |
| `docs/perf/` | CORE | Performance methodology. |
| `docs/Performance_Synthesis.md` | CORE | |
| `docs/Podcast_Infrastructure_Research.pdf` | FIRM | Firm research. |
| `docs/Product_And_Software_Summary.{pdf,tex}` | FIRM | Firm narrative. |
| `docs/Product_Description.pdf` | FIRM | Firm narrative. |
| `docs/Reader_Guide.{pdf,tex}` | FIRM | Firm-specific reader guide. |
| `docs/redteam/` | FIRM | Firm-run red-team material. |
| `docs/research/` | FIRM | All firm-named research (QH benchmark, Cross-Model Geometry, Cross-Domain Transfer, Householder Ablation). Stripped wholesale. |
| `docs/runs/` | FIRM | Run logs. |
| `docs/Schooling_Questions.{pdf,tex}` | FIRM | Founder's children's-education notes. |
| `docs/security/Threat_Model.md` | CORE | Generic threat model (parameterised). |
| `docs/Server_Architecture.pdf` | CORE | Generic. |
| `docs/template/` | CORE | This directory (the inventory itself). |
| `docs/The_Meta_Method.pdf` | CORE | Generic framing of the platform's approach. |
| `docs/Theseus_Codex_User_Guide.{pdf,tex}` | CORE | Generic Codex user guide (replaced by prompt-67 set; both ship). |
| `docs/Transcript_Extraction_Research.pdf` | CORE | Generic infra investigation. |

## noosphere/ subtable {#noosphere-subtable}

The `noosphere/noosphere/` Python package is almost entirely CORE
(ingestion, claim extractor, principle pipeline, Oracle, Currents,
forecasts, equities, safety gates, embeddings, evaluation). The
exceptions:

| Path | Class | Notes |
| ---- | ----- | ----- |
| `noosphere/noosphere/benchmarks/qh_*` | FIRM | Quintin Hypothesis benchmark. Stripped. |
| `noosphere/noosphere/benchmarks/cross_model_runner.py` | FIRM | Cross-Model Geometry runner. |
| `noosphere/noosphere/transfer/` | FIRM | Cross-Domain Transfer Study. |
| `noosphere/noosphere/peer_review/geometric_blindspot.py` | FIRM | Firm-specific finding. |
| `noosphere/noosphere/methods/geometric_blindspot.RATIONALE.md` | FIRM | Firm-specific finding. |
| `noosphere/scripts/run_qh_full.sh` | FIRM | |
| `noosphere/scripts/run_cross_model_full.sh` | FIRM | |
| `noosphere/scripts/build_cross_model_pdf.py` | FIRM | |
| `noosphere/tests/test_qh_*` | FIRM | Benchmark tests. |
| `noosphere/noosphere_data/` | SEED | Empty-by-default. |
| `noosphere/noosphere/founders.py` | CONFIG | Founder-default identifiers tokenised. |

Everything else under `noosphere/noosphere/` ships verbatim as CORE.

## theseus-codex/ subtable {#theseus-codex-subtable}

| Path | Class | Notes |
| ---- | ----- | ----- |
| `theseus-codex/prisma/schema.prisma` | CORE | |
| `theseus-codex/prisma/migrations/` | CORE | |
| `theseus-codex/prisma/seed.ts` | SEED | Ships as the existing minimal seed (Organization + admin Founder from env); the `WITH_MOCK_DATA` block is left intact for tenant choice. The bootstrap wizard invokes it without `SEED_WITH_MOCK_DATA`. |
| `theseus-codex/src/app/methodology/benchmark/qh/` | FIRM | Quintin Hypothesis pages. |
| `theseus-codex/src/app/methodology/geometric_blindspot/` | FIRM | Geometric Blindspot finding. |
| `theseus-codex/src/app/methodology/replicate/` | FIRM | Firm-specific replication landing. |
| `theseus-codex/src/app/methodology/replicators/` | FIRM | Firm-named replicator list. |
| `theseus-codex/src/lib/readerTour.ts` | CONFIG | Tokenised — references the firm's research. |
| `theseus-codex/src/__tests__/*qh*`, `*geometric_blindspot*`, `*reader-guide*` snapshots | FIRM | Stripped together with the firm-only pages. |
| `theseus-codex/public/qh-benchmark/` | FIRM | Generated benchmark site. |
| `theseus-codex/public/sculptures/` | FIRM | Firm-specific amber-bust assets. The fallback render handles absence gracefully. |
| `theseus-codex/dev.db` | SEED | Stripped (regenerated by bootstrap). |
| `theseus-codex/node_modules/` | FIRM | Stripped. |
| `theseus-codex/dist-desktop/` | FIRM | Stripped (build artifact). |
| Everything else under `theseus-codex/` | CORE | App shell, components, lib, worker, tests. |

## theseus-public/ subtable {#theseus-public-subtable}

The public marketing site is CORE — it renders whatever conclusions
and principles the tenant has approved for publication. Specific
content files:

| Path | Class | Notes |
| ---- | ----- | ----- |
| `theseus-public/content/` | SEED | Replaced with an empty-shape directory. |
| `theseus-public/out/` | FIRM | Stripped (Next.js export output). |
| Everything else | CORE | |

## scripts/ subtable {#scripts-subtable}

| Path | Class | Notes |
| ---- | ----- | ----- |
| `scripts/check_*.py` | CORE | Generic invariant checkers. |
| `scripts/build_*.sh` | CORE | Generic doc builders. |
| `scripts/build_template.sh` | CORE | Self-extracting; ships in the template so the template can later be re-built from a customised source. |
| `scripts/template/manifest.yml` | CORE | The manifest itself ships, so tenants can extend it. |
| `scripts/template/test_extraction.py` | CORE | Sanity test for the extractor. |
| `scripts/migrate_production*.sh` | CORE | |
| `scripts/codesign_*` | CORE | |
| `scripts/notarize_macos.sh` | CORE | |
| `scripts/detect_import_cycles.py` | CORE | |
| `scripts/operations_drill_candidates.py` | CORE | |
| `scripts/clear-codex-library.sh` | CORE | |
| `scripts/naming_baseline.json` | CONFIG | Path-prefix tokens. |
| `scripts/no_inline_env_reads_baseline.json` | CONFIG | Path-prefix tokens. |
| `scripts/round*_smoke.sh` | FIRM | Round-specific smoke harnesses. Stripped. |

## Token manifest summary

The full token list is in `scripts/template/manifest.yml`. The
current set:

- `THESEUS_ORG_NAME` — "Theseus" → "<your firm name>"
- `THESEUS_ORG_SLUG` — "theseus-local" → "<your firm slug>"
- `THESEUS_DEFAULT_LLM` — "haiku-4-5" (overridable)
- `THESEUS_NOTIFY_FROM_DEFAULT` — placeholder sender
- `THESEUS_PUBLIC_BASE_URL` — placeholder origin
- `THESEUS_FOUNDER_DISPLAY_NAME` — replaces any remaining bio text

## Excluded-by-rule (always stripped)

- `.env*` except `.env.live.template`
- All `coding_prompts/archive_round*/` and `coding_prompts/ui_ux_round*/`
- `.codex_runs/`, `.claude_code_runs/`
- All generated PDFs except `docs/guides/*.pdf`
- The firm's research benchmark directories listed above
- The founder's name and bio anywhere it appears
- `node_modules/`, `.venv*/`, `dist*/`, `.next/`, `out/`, `.vercel/`
- `dev.db`, `*.sqlite`, `*.db`
