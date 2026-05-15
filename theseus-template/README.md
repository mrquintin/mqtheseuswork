# Theseus Template

This is a tenant-installable copy of the Theseus platform. It carries
the platform mechanism — ingestion, claim extraction, principle
pipeline, the Oracle, Currents, optional Forecasts and Equities
modules, the eight-gate safety contract — without the source firm's
intellectual capital.

The intent matches what the platform's founder described:

> "I also want some kind of way of creating a template … so that we
> can install it in businesses, and we can allow them to capitalize
> on their intellectual capital as best as possible."

A typical adopter is a firm — for instance, a VC firm — whose
partners have a body of written work, podcasts, and talks that the
firm's decisions should be grounded in. The template provides the
mechanism; the tenant provides the corpus.

## What this template gives you

- **Ingestion pipeline** for written sources, transcripts, podcasts.
- **Claim extractor** that surfaces structured assertions from the
  corpus.
- **Principle pipeline** that distills recurring positions into
  named, citable principles.
- **The Oracle** — natural-language interrogation of the corpus,
  grounded in the principles.
- **Currents** — running synthesis of unfolding events through the
  lens of the principles.
- **Forecasts** and **Equities** modules — optional, off by default,
  gated by the eight-gate safety contract.
- **Public surface** — the Codex (authed dashboard) and the public
  marketing site (Next.js).
- **The eight-gate safety contract** is inherited unchanged from
  the platform. Live trading flags ship `false`.

## What this template does NOT give you

The source platform repository carries firm-specific research output
that does not ship here:

- The originating firm's named research benchmarks and ablation
  studies (kept in the source repo as firm intellectual property).
- The originating founder's reading list, written work, and
  podcast/talk recordings.
- The originating firm's seeded conclusions and principles.
- The originating firm's operator runbook entries and bug ledger.

These are firm intellectual property. Each tenant builds their own
equivalent by feeding their own corpus through the same pipeline.

## Bootstrap

```bash
./scripts/bootstrap.sh
```

The wizard asks for:

- organisation display name + slug
- primary admin email and initial password
- Postgres `DATABASE_URL`
- LLM provider + API key (Anthropic, OpenAI, or both)
- whether to enable the Forecasts module
- whether to enable the Equities module

It writes `.env.live` from `.env.live.template`, runs
`prisma migrate deploy` + `alembic upgrade head`, and seeds the
database with **one** Organization row and **one** admin Founder
row. Conclusions and principles start empty — you fill them in by
ingesting your corpus.

Re-run with `--force` to overwrite an existing `.env.live`. Pass
`--non-interactive` if you have prefilled the env in your shell.

## Running locally

After bootstrap:

```bash
# Codex (authed dashboard) — http://localhost:3000
cd theseus-codex && npm install && npm run dev

# Public marketing site — http://localhost:3001
cd theseus-public && npm install && npm run dev

# Noosphere worker (Python)
pip install -r requirements.txt
python -m noosphere
```

## User guides

The platform ships with six PDF user guides under `docs/guides/`:

| Guide | What it covers |
| ----- | -------------- |
| `01_Theseus_Quick_Start.pdf` | What Theseus is and what to read next |
| `02_Knowledge_and_Principles.pdf` | Feeding your corpus and curating principles |
| `03_The_Oracle.pdf` | Asking the system questions |
| `04_Currents.pdf` | Running synthesis of current events |
| `05_Forecasts_and_Portfolio.pdf` | The optional forecasting + portfolio modules |
| `06_Operator_Console.pdf` | Running the platform day-to-day |

Open these first — they're the canonical operator orientation and
describe the surface as it actually exists.

## Safety contract

The Forecasts and Equities modules ship with live-trading flags set
to `false`. The eight-gate safety contract (see
`docs/security/Threat_Model.md`) is unchanged from the platform: do
not turn on `FORECASTS_LIVE_TRADING_ENABLED` or
`EQUITIES_LIVE_TRADING_ENABLED` until you have completed the
operator rehearsal documented in `docs/operator/SCHEDULER_OPS.md`.

## Provenance

This template was produced by an extraction script in the source
Theseus repository. The extraction is deterministic: the same source
produces a byte-identical template (modulo file timestamps). The
template is initialised as its own git repository with a single
initial commit — it carries no history that links back to the
source firm's repo. The extraction tooling itself stays in the
source repo; this template is the artifact.

## Configuration tokens

The bootstrap wizard writes `.env.live` with the values it
collected:

- `THESEUS_ORG_NAME` — your firm name
- `THESEUS_ORG_SLUG` — URL-safe slug
- `THESEUS_DEFAULT_LLM` — default model id (`haiku-4-5`)
- `THESEUS_NOTIFY_FROM` — sender for notifications
- `DATABASE_URL` — Postgres connection string
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — LLM provider keys

Edit `.env.live` directly to change them later.
