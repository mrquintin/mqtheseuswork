# Theseus

## Download installers

**[→ Browse all downloads on the Releases page](https://github.com/mrquintin/mqtheseuswork/releases/latest)**

Direct links (built fresh from `main` on every push):

| Application | macOS | Windows |
|---|---|---|
| **Dialectic** — live conversation analyzer | [Dialectic.dmg](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Dialectic.dmg) | [Dialectic-Setup.exe](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Dialectic-Setup.exe) |
| **Noosphere CLI** — reasoning and ingestion engine | [noosphere-macos.tar.gz](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/noosphere-macos.tar.gz) | [Noosphere-Setup.exe](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Noosphere-Setup.exe) |

If a direct link returns 404, the latest CI run may still be in progress or that specific installer failed to build — the [Releases page](https://github.com/mrquintin/mqtheseuswork/releases) always shows exactly which installers are currently available. Build status: [Actions](https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml).

## Theseus Codex (web)

The **Theseus Codex** is a web application, not a downloadable installer. Access it in your browser:

> **→ [https://www.theseuscodex.com](https://www.theseuscodex.com)**

**New here?** Read the [**Theseus Codex User Guide (PDF)**](docs/Theseus_Codex_User_Guide.pdf) — 10 pages, covers every page, the underlying data pipeline, and four concrete workflows. The same PDF is linked from the **Help** button in the app's top nav.

Contact the admin for founder credentials. Every push to `main` auto-redeploys via Vercel; the Postgres backend lives on Supabase. To run the Codex locally for development, see `theseus-codex/README.md`. For the full deployment runbook (Supabase + Vercel setup, environment variables, troubleshooting), see `docs/Vercel_Supabase_Deploy.md`.

---

Theseus is a research and investment firm building software for recorded, inspectable reasoning. The goal is not only to store what the firm concludes, but to preserve how those conclusions were reached, what sources support them, what objections matter, and what would require revision. This repository is the firm's working monorepo. It holds the desktop tools, the Noosphere processing engine, the public/private Codex web app, deployment scripts, and the written research that motivates them.

## Repository map

The repo is organized so each software artifact lives in its own directory, with a shared `docs/` folder for PDF deliverables.

```
Theseus/
├── noosphere/          Reasoning, ingestion, Currents, and publication engine (Python)
├── dialectic/          Live conversation analyzer (PyQt6 + Whisper + NLI)
├── theseus-codex/      Public site and founder control plane (Next.js 16 / React 19 / Prisma 7)
├── ideologicalOntology/ Research experiments in contradiction geometry
├── reference/          Starting-material snapshots (git-ignored; includes the original theseus-codex prototype)
├── docs/               Published PDFs (research, architecture, product)
└── Podcast talks/      Source transcripts and audio artifacts
```

## Main software surfaces

**Noosphere** is the Python processing engine. It ingests transcripts and writings, extracts claims and source structure, creates methodology profiles, computes embeddings for exploration, runs coherence/adversarial/calibration tools, and writes back to the shared Codex database. It also runs the Currents backend and scheduler: X posts are ingested, relevance-gated against firm conclusions, converted into cited firm opinions, and clustered into public article candidates. See `noosphere/README.md`.

**Dialectic** is the live companion. It listens to a discussion in real time via the microphone, transcribes it with `faster-whisper`, segments the transcript into claims, and displays contradictions, topic drift, and argumentative structure on a PyQt6 dashboard while the conversation is still happening. Its output feeds Noosphere. See `dialectic/README.md`.

**Theseus Codex** is both the public site and the founder control plane. Public pages show reviewed articles, structured responses, forecasts, and Currents opinions. Founder-only pages handle authentication, uploads, transcript/source exploration, library views, embeddings-based exploration, founder Currents, publication review, forecasts, and operations status. Built on Next.js 16, React 19, and Prisma 7 with bcryptjs-gated access. See `theseus-codex/README.md`.

## Written research

The `docs/` folder holds PDFs and operational notes. Some PDFs are research or design documents rather than live product descriptions. For the current high-level product state, start with this README, `METHODOLOGICAL_REORIENTATION.md`, `docs/Operations_Manual.md`, `docs/Vercel_Supabase_Deploy.md`, and `docs/operator/CURRENTS.md`.

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

## Current guiding principle

Every component of this system is built around a practical constraint: reasoning only compounds if later reviewers can inspect the record. Theseus is instrumentation for that record.
