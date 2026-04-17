# Theseus / Noosphere — Operations manual

This document covers day-to-day operation of the Noosphere engine in this monorepo: setup, workflow, failure modes, model upgrades, and backup/restore.

## First-time setup

1. **Python** — Use Python 3.11+.
2. **Dependencies** — From the repo root: `pip install -r noosphere/requirements.txt` (and optional `pip install -e ".[dev]"` if you use the root `pyproject.toml` dev extras).
3. **Configuration** — Environment variables use the prefix `THESEUS_`. Important fields:
   - `THESEUS_DATABASE_URL` — default `sqlite:///./noosphere_data/noosphere.db` (relative to the process working directory unless absolute).
   - `THESEUS_DATA_DIR` — filesystem root for `graph.json`, registries, synthesis output, and related artifacts.
   - Optional `theseus.toml` at the repo root can supply defaults (see `noosphere/noosphere/config.py`).
   - **Theseus Codex** — `DATABASE_URL` is read from `theseus-codex/prisma.config.ts` (Prisma 7). Runtime SQLite uses `@prisma/adapter-better-sqlite3` (`src/lib/prismaAdapter.ts`).
4. **API keys** — Only required for LLM-backed flows: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` depending on `THESEUS_LLM_PROVIDER` / `THESEUS_LLM_MODEL`.

## Daily workflow (record → upload → read advisor)

1. **Record** — Capture audio or export a Dialectic `session.jsonl` (one JSON object per line: `text`, `speaker`, optional `embedding`, optional `claim_id`, `episode_id`).
2. **Upload / ingest** — Use `python -m noosphere ingest …` (Click CLI) or `python -m noosphere.typer_cli` / Typer commands as wired in your environment. Dialectic JSONL is persisted into SQLite via `ingest_dialectic_session_jsonl`.
3. **Graph** — Principles and contradictions live in `graph.json` under `THESEUS_DATA_DIR`. Ingest alone does not rebuild the ontology graph; promotion/distillation or manual graph maintenance is required for synthesis to see principles.
4. **Synthesis assembly** — `noosphere synthesize` runs `run_synthesis_pipeline` (returns a `SynthesisPipelineRun` with `persisted_count`), writing firm-level `Conclusion` rows to SQLite and a small JSON summary under `synthesis/assembly/`.
5. **Research advisor** — `noosphere research --session <episode_id> [--generate]` produces grounded topic/reading JSON under `synthesis/research_sessions/` when `--generate` is set (LLM required).

## Known failure modes and mitigations

| Symptom | Likely cause | Mitigation |
|--------|----------------|------------|
| Synthesis writes zero conclusions | Principles lack ≥2 supporting claims in the graph, or meta-gates fail | Inspect `graph.json`; widen supporting claim attachment; lower conviction to satisfy domain ceiling; see `noosphere/meta_analysis.py` thresholds |
| `session_research` returns validation error | LLM output missing citation ids | Retry with smaller context; tighten prompt; ensure claim ids exist in the graph for that `episode_id` |
| SQLite “database is locked” | Concurrent writers | Keep one writer process; avoid parallel tools hitting the same DB |
| Slow coherence runs | NLI + judge enabled on many pairs | Use cache, reduce scheduled pairs, skip LLM judge for batch jobs |
| Empty contradictions list | No `CONTRADICTS` edges between principles in the graph | Add relationships via ontology tooling or distillation |

## Model upgrade procedure

1. **Pin versions** — Record `THESEUS_EMBEDDING_MODEL_NAME`, NLI model id, and LLM model id in your deployment notes / `theseus.toml`.
2. **Re-embed** — Run `noosphere rebuild-embeddings` (or the embed pass API you use in production) so claim vectors match the new encoder.
3. **Recalibrate** — Refresh coherence calibration bundles if you maintain them under `noosphere/noosphere/coherence/`.
4. **Re-run coherence gold eval** — Execute the coherence regression tests (`noosphere/tests/test_coherence_eval.py` and related fixtures) and confirm macro-F1 stays within the allowed regression tolerance documented beside the fixture.

## Backup and restore

- **Backup** — `noosphere backup` creates `~/.theseus/archives/theseus_backup_<UTC>.tar.gz` with `manifest.json`, the SQLite file as `store.sqlite` (when `THESEUS_DATABASE_URL` is SQLite), and a `data_dir/` tree mirroring your configured data directory.
- **Restore** — `noosphere restore path/to/archive.tar.gz --force` copies files into the current `THESEUS_DATA_DIR` and replaces the SQLite file implied by `THESEUS_DATABASE_URL`. Without `--force`, restore refuses non-empty target directories.

## Logs

Structured logs default to JSON on stdout. With `THESEUS_LOG_FILE` unset or `1`, duplicate JSON lines are written to `~/.theseus/logs/noosphere.jsonl` (rotating). Set `THESEUS_LOG_DIR` to override the directory, or `THESEUS_LOG_FILE=0` to disable the file sink.

## Adversarial coherence (strongest critic)

The adversarial subsystem generates structured objections to firm-level conclusions, formalizes them as **non–founder-authored** claims (`claim_origin=adversarial`), runs the **same six-layer coherence stack** against the conclusion anchor, and persists verdicts in the `adversarial_challenge` table (mirrored in the Theseus Codex Prisma schema when both use the same SQLite file).

### Configuration

- `THESEUS_ADVERSARIAL_ENFORCE` — default `false`. When `true`, the **Severity** meta-criterion requires that the top-`THESEUS_ADVERSARIAL_K` (default 3) challenges for the principle/evidence **fingerprint** are present and none are in `fallen` / `fatal` state (human **addressed** counts as satisfied for Severity).
- `THESEUS_ADVERSARIAL_SHADOW` — when `true`, evaluations and demotions are recorded but **automatic tier demotion** is skipped (shadow / review mode).
- `THESEUS_ADVERSARIAL_STALE_DAYS` — challenges older than this window are flagged **stale** in the UI; re-run `python -m noosphere adversarial` on a cadence (default monthly intent).

### Commands

- `python -m noosphere adversarial --conclusion <NOOSPHERE_CONCLUSION_ID> [--depth 3]` — generate objections, persist challenges, run coherence, apply demotion rules unless shadow mode.
- `python -m noosphere adversarial --all` — all **firm-tier** conclusions in the store.

### Human review protocol (fallen conclusions)

1. **Who** — At least one founder (or delegated reviewer) reads fallen challenges in the portal **Adversarial** page or via the store.
2. **Cadence** — After each adversarial batch and at least monthly when `stale` flags appear.
3. **Actions** — Use `POST /api/adversarial/[challengeId]/override` with `{ "kind": "addressed", "pointer": "…", "notes": "…" }` when the firm has already answered the line of attack in a specific essay or session, or `{ "kind": "fatal", … }` when the objection should **force** the conclusion to **open** tier (portal updates the mirrored `Conclusion` row when ids align).
4. **Re-evaluation triggers** — Evidence chain change, embedding / NLI model upgrade, or explicit CLI re-run after calibration drift.

### Operational note

Point the Theseus Codex `DATABASE_URL` at the **same** SQLite file as `THESEUS_DATABASE_URL` so the `/adversarial` page and APIs can read the `adversarial_challenge` table created by Noosphere’s SQLModel metadata (no separate Prisma migration required for that table).

## Calibration scoreboard (predictive claims)

The firm tracks **falsifiable predictions** (probability or range, resolution date, crisp true/false criteria) in `predictive_claim` with outcomes in `prediction_resolution`. This is not a prediction market; it is an internal epistemic ledger.

### Audit before scoring

1. **Extract** — `python -m noosphere.typer_cli predictive extract --claim-id <UUID> [--no-persist]` runs the LLM second pass; persisted rows start in `draft`.
2. **Confirm** — `python -m noosphere.typer_cli predictive confirm --id <PRED_ID>` marks human review complete and moves the row to `scoring_open`. The system does not treat missing extractions as false negatives for an author; only confirmed rows enter aggregates.
3. **Resolve** — `python -m noosphere.typer_cli predictive resolve --id <PRED_ID> --outcome 0|1 --justification "…" [--evidence-artifacts id1,id2] [--resolver founder]` records a **manual** resolution. Every resolution must carry substantive justification and, when possible, artifact ids pointing at evidence (URLs or ingested artifact ids). Silent or vibe-based resolution is invalid operational practice.
4. **Unclear criteria** — `python -m noosphere.typer_cli predictive flag-unclear --id <PRED_ID>` sets `open_unclear` for refinement; excluded from Brier aggregates.

### Honest uncertainty

Predictions whose probability midpoint lies in **[0.45, 0.55]** are treated as **honest uncertainty**: they do not enter Brier/log-loss aggregates (they neither reward nor penalize domain calibration curves).

### Scoring and exports

- **JSON** — `python -m noosphere.typer_cli scoreboard` prints per-author/domain Brier and log-loss, decile calibration bins, and a weak-domain list for the research advisor.
- **Codex** — `/scoreboard` reads the same SQLite tables; use `?author=` for drill-down. Append `?engage=1` to show full prediction text during deliberate review.

### Synthesis discount (feature-flagged)

- **`THESEUS_CALIBRATION_CONFIDENCE_ENABLED`** — default `false`. When `true`, synthesis sets `Conclusion.calibration_adjusted_confidence` using **Beta(0.5, 0.5) smoothing** on the empirical resolution rate in the **decile bin** of the author’s past predictions that matches the stated confidence (domain-specific pool, then pooled across domains for the same author if the bin has fewer than five trials). `Conclusion.confidence` remains the model’s stated value; the note field records the pooling path and trial count. Turn the flag on only after founder review of the rule.

### Research advisor

When resolved prediction data exist, the advisor injects a short **calibration signal** block into topic selection (domains with high mean Brier on scored predictions), nudging the next brief toward empirical work where the firm is least calibrated.

## Belief-state replay (time-machine)

The goal is not “what would we believe with today’s model?” but **what rows are consistent with evidence whose effective time is on or before a chosen calendar day**, and (for synthesis) **dry-run assembly** over a filtered claim set.

### Schema

- **Artifacts** carry `effective_at`, `superseded_at`, and `effective_at_inferred` (SQLite columns, backfilled on open). When `effective_at` is omitted at ingest, it defaults from `source_date` (end of that UTC day) when present, otherwise from `created_at`.
- **Store.get_state_as_of(date)** returns claim and artifact id sets consistent with that cutoff (wrapper around the same rules as `noosphere.temporal_replay`).
- **Claims** carry the same three fields in their JSON payload; when unset, replay derives time from the linked artifact or from `episode_date`.
- **Conclusions** may carry `superseded_at` and `supersedes_conclusion_ids` for lineage (optional; not auto-populated in the first pass).

### Imperfections (must be disclosed)

- **Embeddings and cluster IDs** reflect the current encoder and graph distillation, not the historical encoder weights. The `embedding_model_version` table records which model name was pinned from which date; until you add one row per real upgrade, the CLI and APIs emit warnings about encoder drift.
- **Ontology graph** (`graph.json`) is filtered in memory for replay commands, but the graph file itself is not rewritten; replay is a *read projection*.
- **Codex** — `/conclusions?asOf=…` uses Noosphere replay rules when `NOOSPHERE_DATABASE_URL` is set. `/contradictions` and `/founders` filter Prisma rows by `createdAt` ≤ end of the chosen UTC day: a practical UI approximation, not the full coherence-pair replay.

### Commands

- `python -m noosphere as-of YYYY-MM-DD claims-count` — count claims visible on that cutoff (artifact + supersession rules).
- `python -m noosphere as-of YYYY-MM-DD conclusions` — JSON list of stored conclusions that pass replay consistency (synthesized by cutoff, evidence visible on cutoff).
- `python -m noosphere as-of YYYY-MM-DD synthesize` — **dry-run** synthesis previews (`dry_run: true`); does not write conclusions.
- `python -m noosphere diff YYYY-MM-DD YYYY-MM-DD` — structured JSON diff; add `--narrative` for a short grounded summary (LLM when API keys exist).
- `python -m noosphere counterfactual --without-artifact <id> [--as-of YYYY-MM-DD]` — dry-run synthesis excluding claims tied to that artifact.

### Caching

Replay is deterministic from store + graph; week-bucket caching of previews is not enabled by default. For heavy UIs, cache JSON by `(as_of_week, command)` at the edge.

## External literature and research advisor

- **Ingest** — `python -m noosphere literature local-pdf /path/to/paper.pdf [--license firm_licensed|open_access|restricted_metadata_only]` (optional sidecar `paper.json` with `title`, `author`, `date`). `python -m noosphere literature arxiv --query 'cat:physics.soc-ph' [--max 5] [--pdf]` pulls open-access abstracts (PDF text only with `--pdf`, slow).
- **Index** — `python -m noosphere literature index` rebuilds the SQLite FTS5 table used for hybrid retrieval (BM25 + optional dense rerank when claim embeddings exist).
- **PhilPapers** — set `PHILPAPERS_API_KEY`; connector is stubbed until a stable API surface is wired.
- **Copyright** — `Artifact.license_status` records posture. Do not store full text for `restricted_metadata_only`; the advisor only retrieves claims that exist in the store.
- **Research advisor** — `session_research(..., generate=True)` now **retrieves first** (hybrid index over founder + voice + literature claims). If the index returns no hits, generation is skipped with `no_retrieval_hits`. Each reading suggestion must include `grounding_claim_id` from the retrieval block; ungrounded LLM output is rejected at validation. Successful readings append rows to the **reading queue** (`reading_queue` SQLite table), visible under `/reading-queue` in the Codex when `NOOSPHERE_DATABASE_URL` is set.

## Cloud multi-tenant (productionization)

This section tracks **Strategic Prompt 06**: durable cloud deployment, tenant isolation, and worker separation — without abandoning the **local / desktop** deployment path.

### What is implemented in-repo today

- **Prisma**: `Organization` model plus `organizationId` on all tenant-scoped portal tables; composite uniqueness on `(organizationId, email)` and `(organizationId, username)`. Login resolves `(organizationSlug, email)`; seed creates org `theseus-local`.
- **Prisma 7**: connection URL lives in `theseus-codex/prisma.config.ts`; runtime uses `@prisma/adapter-better-sqlite3` for `file:` URLs (`src/lib/prismaAdapter.ts`). PostgreSQL requires wiring `@prisma/adapter-pg` in the same module before switching `DATABASE_URL` to `postgresql://…`.
- **Codex scoping**: dashboard, conclusions, founders, upload fetch, and adversarial conclusion updates filter by the authenticated founder’s `organizationId`.
- **Worker split**: when `REDIS_URL` and `USE_JOB_QUEUE=1` are set, uploads enqueue to Redis; run **`npm run worker:ingest`** (separate process) to execute the same `processUpload` path. Otherwise ingest runs in-process (laptop mode).
- **Object storage**: `noosphere/noosphere/storage_client.py` — `LocalDiskStorage` and S3-compatible backend (`STORAGE_BACKEND=s3`, `boto3` required).
- **Tenancy (Noosphere)**: `noosphere/noosphere/tenancy.py` introduces `TenantContext`; SQLModel store tables do **not** yet enforce `organization_id` on every row (next migration tranche).
- **Containers / Helm**: `deploy/docker/`, `deploy/helm/theseus/`, `deploy/compose/docker-compose.yml`, and `deploy/README.md`.
- **RLS template**: `deploy/sql/postgres_rls_example.sql` — apply after Postgres migration; set `SET LOCAL app.current_org_id = '…'` per request in the app or pooler middleware.
- **Observability pointers**: `deploy/observability/README.md`.

### What is still explicit follow-up

- **SSO (Google / Microsoft)** — add NextAuth (or similar) and map IdP subjects to `(organizationId, founder)`; keep bcrypt for personal-tier.
- **Secrets** — Doppler / AWS Secrets Manager / Sealed Secrets; never bake secrets into images.
- **BYOK / per-tenant LLM keys** — extend `noosphere/llm.py` to load tenant credentials from your secret store; decrypt only in the worker; zero in memory after the job.
- **Noosphere Postgres + Alembic** — mirror Prisma’s move; add `organization_id` to `artifact`, `claim`, `predictive_claim`, etc., before enabling RLS on those tables.
- **Cost accounting** — token + storage meters to `/admin` (operator) and optional tenant views.
- **Dialectic desktop** — see `deploy/docker/dialectic-desktop/README.md` (PyInstaller vs Tauri vs Electron).

### Backup, disaster recovery, and tenant export

1. **Postgres**: nightly logical dumps (`pg_dump`) to an object store bucket in a **second region**; retention ≥ 30 days. Restore drill: provision empty DB, `pg_restore`, run Prisma migrate status, smoke-test **two** orgs with canned queries that must return **zero** cross-tenant rows.
2. **Object storage**: enable cross-region replication on the artifacts bucket; treat the bucket as part of backup scope.
3. **Per-tenant export** (SLA: e.g. 24h): job that packages Postgres rows for `organizationId = X` (all Prisma tables) plus Noosphere blobs referenced by `storage_uri` / `content_sha256`, plus `graph.json` slices if the tenant owns a graph partition — output signed tarball; verify checksum list in the audit log.
4. **Deletion**: soft-delete org (`Organization.deletedAt`) for 30 days, then hard-delete export bundle keys and DB rows in a single transaction per tenant.

### Desktop-only mode (first-class)

The SQLite + local disk path remains supported: omit `REDIS_URL` / `USE_JOB_QUEUE`, keep `DATABASE_URL=file:./dev.db`, and run Noosphere on the same machine as the portal. No cloud dependency is required for serious single-user use.

## Researcher API (external methodology surface)

Separate **FastAPI** service in `researcher_api/` — capability-only endpoints on **researcher-supplied** payloads; it does **not** read firm conclusions or cross-tenant store data.

### Run (development)

From the repo root, with `noosphere/` on `PYTHONPATH`:

```bash
export RESEARCHER_API_KEYS='lab:sandbox-lab:sk-your-long-secret-here'
export PYTHONPATH="$PWD/noosphere${PYTHONPATH:+:$PYTHONPATH}"
uvicorn researcher_api.main:app --reload --port 8080
```

OpenAPI UI: `http://127.0.0.1:8080/docs`.

### Environment

| Variable | Purpose |
|----------|---------|
| `RESEARCHER_API_KEYS` | Comma-separated `label:sandbox_tenant:secret` triples (see `researcher_api/researcher_api/config.py`). |
| `RESEARCHER_API_RATE_LIMIT_PER_HOUR` | Per-key per-route sliding window (default `120`). |
| `THESEUS_RESEARCHER_AUDIT_LOG` | JSONL audit path (default `~/.theseus/researcher_api_audit.jsonl`). |
| `THESEUS_GIT_SHA` | Injected into `X-Theseus-Git-SHA` (Docker build arg in `deploy/docker/researcher-api/Dockerfile`). |
| `RESEARCHER_API_COHERENCE_JUDGE` | When truthy, allows LLM judge **only** if the client includes `"judge"` in `layers`. |
| `THESEUS_*` | Shared Noosphere settings for extract / embed / LLM when those code paths run. |

### Container

`deploy/docker/researcher-api/Dockerfile` — build with `--build-arg THESEUS_GIT_SHA=$(git rev-parse HEAD)`.

### Audit retention

Operator policy: **24 months** JSONL retention for researcher API audit lines; rotate and archive to cold storage if compliance requires longer immutability with access controls.

### Security / coordinated disclosure

The Researcher API serves `GET /security` as plain text from `docs/researcher-api/SECURITY.md`. Bundle that file in the API image (alongside method notes) if you deploy from a slim context.

## Red-team and robustness (SP08)

Internal attack taxonomy, synthetic generators, and mitigated regression checks live in `noosphere/redteam.py` and `noosphere/mitigations/`. The public-facing ledger is `docs/Robustness_Ledger.md` (optional PDF via `scripts/build_robustness_ledger_pdf.sh` when Pandoc is installed).

### Commands

```bash
export PYTHONPATH="$PWD/noosphere${PYTHONPATH:+:$PYTHONPATH}"
python -m noosphere redteam taxonomy   # attack class registry + status
python -m noosphere redteam run        # CI mitigated checks (exit non-zero on regression)
```

### CI

GitHub Actions workflow `.github/workflows/noosphere-redteam.yml` runs on pulls that touch coherence, ingestion, mitigations, or the red-team suite.

### Founder rotation

See `docs/redteam/FOUNDER_ROTATION.md` for the monthly sponsor checklist.

## Dialectic interlocutor (live deliberation, SP09)

The PyQt dashboard (`dialectic/dialectic/dashboard.py`) can run **Theseus** as a consent-gated interlocutor: contradiction prompts, open-thread prompts, and prediction-resolution prompts. **Silent** remains the default; each recording session opens a dialog for mode (passive / conversational / tutor), participant opt-in, and optional TTS.

### Artifacts

- Per-session JSONL: `session_<timestamp>_interventions.jsonl` under `DialecticConfig.recordings_dir`.
- Reflection bundle for founder review: `session_<timestamp>_reflection.json` (written on stop).

### Theseus Codex

Set `DIALECTIC_REFLECTIONS_DIR` to the directory containing those `*_reflection.json` files, then open `https://<codex>/sessions/<session_id>/reflection` (same stem as the filename without `_reflection.json`).

### TTS

Local-first: `pyttsx3` or macOS `say` when `DIALECTIC_TTS=1`. Remote TTS is a non-goal for the default path; if you add a cloud voice, send **only** the interlocutor line, not surrounding transcript (privacy).

### Operational discipline (first months)

Review the reflection page within **24 hours** of any non-silent session; track “annoying” vs “high value” to retune `InterlocutorConfig` thresholds in `dialectic/dialectic/config.py`.

## Public knowledge output (SP10)

The firm’s public “published mind” is intentionally **not** a blog or social feed. It is a **structured, versioned, citable** surface built from **PublishedConclusion** snapshots, with an internal **PublicationReview** gate in the Theseus Codex.

### Publication policy (internal)

1. **No auto-publish** — Nothing becomes public without an explicit founder publish action after review.
2. **Eligibility (intent)** — Queue entries are restricted to **firm-tier** conclusions in software; operational policy still expects meta-analysis, adversarial engagement, and founder clarity checks before publish.
3. **Checklist** — Publishing requires explicit confirmation of: meta-analysis, adversarial engagement, clarity, no leakage of private context, and no inadvertent harms.
4. **Exit conditions discipline** — Every published revision must include non-empty **exit conditions** (“what would change our mind”). This is enforced in the publish API/UI.
5. **Headline confidence** — The public headline is the **calibration-discounted** confidence; stated/model confidence is shown as context with an explicit discount reason.
6. **Immutability** — Each material revision creates a new `PublishedConclusion` row (`slug`, monotonically increasing `version`). Older `/c/<slug>/v/<n>` URLs remain valid export targets for citation stability.
7. **Artifacts** — Raw transcripts, full internal claim chains, and reflection bundles are **never** auto-exported. The publication review is the last line against accidental disclosure.

### Export → static site

1. In the Theseus Codex, use **`GET /api/publication/export`** (authenticated) to download the `theseus.publishedExport.v1` JSON bundle.
2. Copy/replace `theseus-public/content/published.json` with that bundle (or automate the copy as part of your deploy pipeline).
3. Build the static site: `npm run build` in `theseus-public/` (this runs `scripts/write-feeds.mjs` to emit `public/feed.xml` and `public/atom.xml`).
4. Serve `theseus-public/out/` from a CDN. Reads should be static; writes remain on the portal APIs.

### Zenodo / DOI minting

Set `THESEUS_ZENODO_TOKEN` on the Theseus Codex server environment used for publishing. Without a token, the publisher stores a **preview DOI** string for pipeline testing (not a registered DOI). Set `THESEUS_PUBLIC_SITE_URL` so generated citation blocks point at the real public origin.

### Structured responses (moderation)

Public submissions are **`POST /api/public/responses`** (CORS-controlled via `THESEUS_PUBLIC_CORS_ORIGINS`). They always create **`PublicResponse` rows in `pending`**.

1. **No anonymity** — Email is required; pseudonymous display is allowed but flagged.
2. **Verified identities** — ORCID is optional but should be treated as a stronger signal in moderation.
3. **No threading** — Approved responses render as a structured list, not nested comment threads.
4. **Promotion** — `engaged` is reserved for responses that should force an internal re-review of the conclusion.

### Weekly email digest (non-goal for code defaults)

RSS/Atom is generated at build time from the published bundle. A weekly email digest is policy-compatible but not implemented in-repo by default; if you add it, keep it **aggregate-only** (no behavioral tracking).

## Regression tests

End-to-end coverage lives in `tests/e2e/test_phase7_pipeline.py`. A lighter performance guard is in `tests/e2e/test_synthesis_perf_subset.py`. Set `THESEUS_SKIP_PERF=1` in CI if the subset test is too noisy for a given runner.

Researcher API unit tests: `python3 -m pip install -e researcher_api[dev]` then `PYTHONPATH=researcher_api:noosphere python3 -m pytest researcher_api/tests -q` from the repo root (the first `PYTHONPATH` segment avoids resolving `researcher_api` to the monorepo folder).
