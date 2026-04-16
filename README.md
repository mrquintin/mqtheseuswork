# Theseus

> **[Latest Release](https://github.com/mrquintin/mqtheseuswork/releases/latest)**

| Application | macOS | Windows |
|---|---|---|
| **Dialectic** — live conversation analyzer | [Dialectic `.dmg`](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Dialectic.dmg) | [Dialectic `.exe`](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Dialectic-Setup.exe) |
| **Noosphere CLI** — epistemological engine | [Noosphere `.tar.gz`](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/noosphere-macos.tar.gz) | [Noosphere `.exe`](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Noosphere-Setup.exe) |
| **Founder Portal** — desktop control plane | [Founder Portal `.dmg`](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Theseus-Founder-Portal.dmg) | [Founder Portal `.exe`](https://github.com/mrquintin/mqtheseuswork/releases/latest/download/Theseus-Founder-Portal-Setup.exe) |

> **Note:** Installers are attached to [GitHub Releases](https://github.com/mrquintin/mqtheseuswork/releases) and built automatically when a version tag (`v*`) is pushed. If the direct links above return 404, visit the [Releases page](https://github.com/mrquintin/mqtheseuswork/releases) and download from the latest draft release.

---

Theseus is an intellectual capital firm pursuing *methodological* truth-finding: the goal is not to stake out substantive claims about the world, but to build and operate the instruments by which disciplined groups of people can converge on better beliefs. This repository is the firm's working monorepo. It holds three pieces of software and the written research that motivates them.

## Repository map

The repo is organized so each software artifact lives in its own directory, with a shared `docs/` folder for PDF deliverables and a `theseus-codex/` for long-running reference material.

```
Theseus/
├── noosphere/          Brain of the Firm — epistemological engine (Python)
├── dialectic/          Live conversation analyzer (PyQt6 + Whisper + NLI)
├── founder-portal/     Founders' web portal (Next.js 16 / React 19 / Prisma 7)
├── ideologicalOntology/ Research experiments in contradiction geometry
├── theseus-codex/      Reference documents and project memory (Next.js)
├── docs/               Published PDFs (research, architecture, product)
└── Podcast talks/      Source transcripts and audio artifacts
```

## The three softwares

**Noosphere** is the core epistemic engine. It ingests podcast transcripts and writings by the firm's founders, decomposes them into atomic claims, evaluates those claims across six complementary coherence methods (natural-language inference, formal argumentation, probabilistic consistency, embedding-geometry tests, information-theoretic compressibility, and an LLM judge), tracks how positions evolve over time, and synthesizes conclusions at three confidence tiers. The engine is the firm's memory and its reasoning substrate. See `noosphere/README.md`.

**Dialectic** is the live companion. It listens to a discussion in real time via the microphone, transcribes it with `faster-whisper`, segments the transcript into claims, and displays contradictions, topic drift, and argumentative structure on a PyQt6 dashboard while the conversation is still happening. Its output feeds Noosphere. See `dialectic/README.md`.

**Founder Portal** is the web-facing control plane. It is where founders authenticate, upload transcripts and writings, trigger Noosphere processing, and inspect the resulting conclusions, contradictions, and research-advisor suggestions. Built on Next.js 16, React 19, and Prisma 7 with bcryptjs-gated access. See `founder-portal/README.md`.

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

# Founder Portal
cd founder-portal && npm install && npm run dev
```

## Guiding principle

Every component of this system is built around one conviction: the scarce resource in knowledge work is not information but *discipline*. Theseus is instrumentation for that discipline.
