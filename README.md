# Theseus

## Download installers

**[→ Browse all downloads on the Releases page](https://github.com/mrquintin/mqtheseuswork/releases/latest)**

Direct links (built fresh from `main` on every push):

| Application | macOS | Windows |
|---|---|---|
| **Dialectic** — live conversation analyzer | [Dialectic.dmg](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Dialectic.dmg) | [Dialectic-Setup.exe](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Dialectic-Setup.exe) |
| **Noosphere CLI** — epistemological engine | [noosphere-macos.tar.gz](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/noosphere-macos.tar.gz) | [Noosphere-Setup.exe](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Noosphere-Setup.exe) |

If a direct link returns 404, the latest CI run may still be in progress or that specific installer failed to build — the [Releases page](https://github.com/mrquintin/mqtheseuswork/releases) always shows exactly which installers are currently available. Build status: [Actions](https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml).

## Theseus Codex (web)

The **Theseus Codex** is a web application, not a downloadable installer. Access it in your browser:

> **→ [https://mqtheseuswork-qiw6.vercel.app](https://mqtheseuswork-qiw6.vercel.app)**

**New here?** Read the [**Theseus Codex User Guide (PDF)**](docs/Theseus_Codex_User_Guide.pdf) — 10 pages, covers every page, the underlying data pipeline, and four concrete workflows. The same PDF is linked from the **Help** button in the app's top nav.

Contact the admin for founder credentials. Every push to `main` auto-redeploys via Vercel; the Postgres backend lives on Supabase. To run the Codex locally for development, see `theseus-codex/README.md`. For the full deployment runbook (Supabase + Vercel setup, environment variables, troubleshooting), see `docs/Vercel_Supabase_Deploy.md`.

---

Theseus is an intellectual capital firm pursuing *methodological* truth-finding: the goal is not to stake out substantive claims about the world, but to build and operate the instruments by which disciplined groups of people can converge on better beliefs. This repository is the firm's working monorepo. It holds three pieces of software and the written research that motivates them.

## Repository map

The repo is organized so each software artifact lives in its own directory, with a shared `docs/` folder for PDF deliverables.

```
Theseus/
├── noosphere/          Brain of the Firm — epistemological engine (Python)
├── dialectic/          Live conversation analyzer (PyQt6 + Whisper + NLI)
├── theseus-codex/      Founders' web codex / control plane (Next.js 16 / React 19 / Prisma 7)
├── ideologicalOntology/ Research experiments in contradiction geometry
├── reference/          Starting-material snapshots (git-ignored; includes the original theseus-codex prototype)
├── docs/               Published PDFs (research, architecture, product)
└── Podcast talks/      Source transcripts and audio artifacts
```

## The three softwares

**Noosphere** is the core epistemic engine. It ingests podcast transcripts and writings by the firm's founders, decomposes them into atomic claims, evaluates those claims across six complementary coherence methods (natural-language inference, formal argumentation, probabilistic consistency, embedding-geometry tests, information-theoretic compressibility, and an LLM judge), tracks how positions evolve over time, and synthesizes conclusions at three confidence tiers. The engine is the firm's memory and its reasoning substrate. See `noosphere/README.md`.

**Dialectic** is the live companion. It listens to a discussion in real time via the microphone, transcribes it with `faster-whisper`, segments the transcript into claims, and displays contradictions, topic drift, and argumentative structure on a PyQt6 dashboard while the conversation is still happening. Its output feeds Noosphere. See `dialectic/README.md`.

**Theseus Codex** is the web-facing control plane. It is where founders authenticate, upload transcripts and writings, trigger Noosphere processing, and inspect the resulting conclusions, contradictions, and research-advisor suggestions. Built on Next.js 16, React 19, and Prisma 7 with bcryptjs-gated access. See `theseus-codex/README.md`.

## Written research

The `docs/` folder holds the PDFs that justify and constrain the software. The most relevant for understanding the system as a whole are `Product_Description.pdf` (how the three softwares fit together), `The_Meta_Method.pdf` (the firm's methodological commitments), `Geometry_of_Unresolution.pdf` (the mathematical treatment of epistemic unresolvability), and `Noosphere_Project_Status.pdf` (engineering status).

## Noosphere logs, backup, and restore

Structured JSON logs go to stdout from the CLI, and (unless `THESEUS_LOG_FILE=0`) are also appended to a rotating file under `~/.theseus/logs/noosphere.jsonl`. Override the directory with `THESEUS_LOG_DIR`.

After `pip install -r noosphere/requirements.txt`, use the Typer CLI entrypoint (see `noosphere/README.md`) for:

- `noosphere backup` — writes `~/.theseus/archives/theseus_backup_<UTC-timestamp>.tar.gz` containing the SQLite file (when using SQLite), the full Noosphere `data_dir` (embeddings on disk, `graph.json`, registries, synthesis output), and a `manifest.json`.
- `noosphere restore <archive.tar.gz> --force` — restores into the configured `THESEUS_DATA_DIR` and SQLite path from `THESEUS_DATABASE_URL`. Use `--force` when the data directory is non-empty.

Operational detail, failure modes, and model-upgrade steps are in `docs/Operations_Manual.md`.

## Running the stack

Each software has its own install instructions. In brief:

```
# Noosphere
cd noosphere && pip install -r requirements.txt
python -m noosphere --help

# Dialectic
cd dialectic && pip install -r requirements.txt
python run.py

# Theseus Codex
cd theseus-codex && npm install && npm run dev
```

## Running currents locally

The "currents" stack — `current_events_api` (FastAPI) + `noosphere.currents`
scheduler loop + `theseus-public` (Next.js hybrid) — has its own compose file,
separate from the canonical `docker-compose.yml` used for the Theseus Codex +
Postgres dev stack.

```bash
# 1. One-time setup
cp .env.example .env
# Fill in X_BEARER_TOKEN and ANTHROPIC_API_KEY in .env.

# 2. Build and run everything
docker compose -f docker-compose.currents.yml up --build

# 3. Visit:
#    - Public site:   http://localhost:3001
#    - API:           http://localhost:8088
#    - API healthz:   http://localhost:8088/healthz
#    - API metrics:   http://localhost:8088/metrics
```

The `currents-migrate` service runs `alembic upgrade head` once at startup and
exits; `currents-api` and `currents-scheduler` are gated on its successful
completion. All three Python services share a named volume (`currents-data`)
mounted at `/data/noosphere` for the SQLite store and `currents_status.json`
heartbeat written by the scheduler.

To shut down and preserve data:

```bash
docker compose -f docker-compose.currents.yml down
```

To shut down and wipe the currents volume:

```bash
docker compose -f docker-compose.currents.yml down -v
```

## Deploying

Two supported modes for the currents stack:

1. **All-in-containers (self-hosted).** Run `docker-compose.currents.yml` on a
   single host with persistent storage attached to the `currents-data` volume.
   Put a TLS-terminating reverse proxy (Caddy, Traefik, nginx) in front of
   ports 3001 and 8088. Set `CURRENTS_CORS_ORIGINS` to your public origin.

2. **Hybrid: Vercel for theseus-public + self-hosted current_events_api.**
   The Next.js app runs on Vercel in its standard Node runtime; route handlers
   under `/api/currents/*` proxy to `CURRENTS_API_URL` (which must be a public
   HTTPS URL pointing at your self-hosted API container). See
   [`ops/deploy-vercel.md`](ops/deploy-vercel.md) for the full runbook,
   including required Vercel environment variables and caveats about SSE on
   Vercel's runtime tiers.

The scheduler loop (`noosphere.currents loop`) is not a Vercel-compatible
workload — it must run on a long-lived host in both modes.

## Testing

The currents stack has four layers of automated tests. None of them call
the real X or Anthropic APIs — fakes under `noosphere/tests/fakes/` stand
in for both.

```bash
# 1. noosphere python tests (unit + integration)
cd noosphere
pytest -q                                # full suite
pytest -q tests/e2e tests/regression     # prompt-17 end-to-end + invariants
cd ..

# 2. current_events_api (FastAPI) tests
cd current_events_api
pytest -q
cd ..

# 3. theseus-public Vitest unit tests
cd theseus-public
npx vitest run src/__tests__/
cd ..

# 4. Playwright smoke test (opt-in)
cd theseus-public
npm i                        # first run: installs @playwright/test
npx playwright install       # first run: downloads Chromium
npm run test:e2e
cd ..
```

The `tests/e2e` suite covers one full pipeline trace: ingest (fake X
client) → enrich → relevance → generate (fake Anthropic client) → persist
→ `/v1/currents` response → SSE fan-out.

The `tests/regression` suite covers the six load-bearing invariants:
citation integrity, abstention correctness, budget enforcement, follow-up
rate limiting, follow-up fresh retrieval, prompt-injection resistance, and
revoked-opinion propagation.

Playwright is deliberately kept out of the default `npm test` — it needs
a running dev server and a downloaded Chromium, so it's a manual
pre-deploy check rather than a per-commit gate.

## Guiding principle

Every component of this system is built around one conviction: the scarce resource in knowledge work is not information but *discipline*. Theseus is instrumentation for that discipline.
