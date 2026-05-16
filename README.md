# Theseus

**A philosopher in a box.**

Theseus is a philosopher in a box. We extract principles from a curated corpus, build logical algorithms that apply those principles to live observations of the world, and place bets when the algorithms predict outcomes the principles support. We are the Renaissance Technologies of formal logic — the same machine shape (inputs → engine → conclusions → bets), one level of abstraction higher. We do not commercialize this. The machine is our edge.

## Why Theseus exists

Quantitative firms abstract numerical patterns out of price data and arbitrage them. The next layer up — patterns inside text, the principles that underwrite arguments — is mostly unworked. Theseus exists to industrialise that layer: a synthesizer trained on a curated corpus emits principles; algorithms execute those principles against live observations; conclusions, memos, and bets are the downstream artifacts. Capital decisions are one way we make the reasoning accountable; calibration is the other.

## Repository structure

The repo is a monorepo with three core software components, supporting research, and shared documentation.

```
Theseus/
├── theseus-codex/     Public site and founder control plane (Next.js 16 / React 19 / Prisma 7)
├── noosphere/         Reasoning, ingestion, Currents, synthesizer, algorithm engine (Python)
├── dialectic/         Live conversation analyzer (PyQt6 + Whisper + NLI)
├── docs/              Published PDFs (research, architecture, product, pitch)
├── coding_prompts/    The round-by-round build prompts that drive the system forward
└── ideologicalOntology/ Research experiments in contradiction geometry
```

The three components correspond directly to the three layers of the machine:

- **theseus-codex** is the workspace and the public face — the founder uploads sources, reviews conclusions, publishes memos; the public reads Currents, Forecasts, Memos, Algorithms, Principles, and the knowledge graph.
- **noosphere** is the engine — it ingests, extracts, synthesizes, runs the algorithms, and writes back to the shared Codex database. Currents and Forecasts both run out of here.
- **dialectic** is the live companion — it listens to a discussion in real time, segments claims, surfaces contradictions, and feeds the result back into Noosphere.

## Where to read next

- **The full positioning, axioms, Renaissance comparison, and reading guide for the public surfaces** → [About page](https://www.theseuscodex.com/about) (source: `theseus-codex/src/app/about/page.tsx`).
- **The pitch deck** → [`docs/pitch/2026_philosopher_in_a_box/deck.pdf`](docs/pitch/2026_philosopher_in_a_box/deck.pdf). Built with `pdflatex` from `deck.tex`; the slide-11 numbers are pulled from the live DB at build time.
- **The three-minute pitch script** → [`docs/pitch/three_minute_script.md`](docs/pitch/three_minute_script.md).
- **Methodology** → `METHODOLOGICAL_REORIENTATION.md`, `THE_META_METHOD.md`, and the public methodology surface at `/methodology`.
- **Operations** → `docs/Operations_Manual.md`, `docs/Vercel_Supabase_Deploy.md`, `docs/operator/CURRENTS.md`.

## Codex (web)

The Theseus Codex is a web application, not a downloadable installer:

> **→ [https://www.theseuscodex.com](https://www.theseuscodex.com)**

New here? Read the [Theseus Codex User Guide (PDF)](docs/Theseus_Codex_User_Guide.pdf) — 10 pages, every page, the underlying pipeline, four workflows. The same PDF is linked from the Help button in the app's top nav.

Contact the admin for founder credentials. Every push to `main` auto-redeploys via Vercel; the Postgres backend lives on Supabase. To run the Codex locally for development, see `theseus-codex/README.md`. For the full deployment runbook, see `docs/Vercel_Supabase_Deploy.md`.

## Desktop installers (Dialectic + Noosphere CLI)

**[→ Browse all downloads on the Releases page](https://github.com/mrquintin/mqtheseuswork/releases/latest)**

Direct links (built fresh from `main` on every push):

| Application | macOS | Windows |
|---|---|---|
| **Dialectic** — live conversation analyzer | [Dialectic.dmg](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Dialectic.dmg) | [Dialectic-Setup.exe](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Dialectic-Setup.exe) |
| **Noosphere CLI** — reasoning and ingestion engine | [noosphere-macos.tar.gz](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/noosphere-macos.tar.gz) | [Noosphere-Setup.exe](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Noosphere-Setup.exe) |

Build status: [Actions](https://github.com/mrquintin/mqtheseuswork/actions/workflows/rolling-release.yml).

## Running the stack locally

Each component has its own install instructions. In brief:

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

## Noosphere logs, backup, and restore

Structured JSON logs go to stdout from the CLI, and (unless `THESEUS_LOG_FILE=0`) are also appended to a rotating file under `~/.theseus/logs/noosphere.jsonl`. Override the directory with `THESEUS_LOG_DIR`.

After `pip install -r noosphere/requirements.txt`, use the Typer CLI entrypoint (see `noosphere/README.md`) for:

- `noosphere backup` — writes `~/.theseus/archives/theseus_backup_<UTC-timestamp>.tar.gz` containing the SQLite file (when using SQLite), the full Noosphere `data_dir` (embeddings, `graph.json`, registries, synthesis output), and a `manifest.json`.
- `noosphere restore <archive.tar.gz> --force` — restores into the configured `THESEUS_DATA_DIR` and SQLite path from `THESEUS_DATABASE_URL`. Use `--force` when the data directory is non-empty.

Operational detail, failure modes, and model-upgrade steps are in `docs/Operations_Manual.md`.

## What Theseus is not

Theseus is not a SaaS product. The reasoning architecture is our edge. The public surfaces — Currents, Forecasts, Memos, Algorithms, Principles, Knowledge graph — are the firm thinking in public. They are not the product.
