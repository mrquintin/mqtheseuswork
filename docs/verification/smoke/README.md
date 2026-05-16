# Smoke harness

A single command that boots the full stack against fixtures, hits
every public route, exercises every CLI subcommand's `--help`, ticks
every scheduler sub-loop once, and runs three end-to-end pipeline
happy paths. The harness FAILS if anything returns 500, crashes, or
silently no-ops.

This is the safety net that catches "everything builds but the
running system is broken" — regressions where the type-checker, the
unit tests, and the migrations are all green but the actual running
process is broken.

## Running locally

```sh
./scripts/smoke/run.sh
```

Single section:

```sh
./scripts/smoke/run.sh frontend-routes
./scripts/smoke/run.sh api-endpoints
./scripts/smoke/run.sh cli-help
./scripts/smoke/run.sh scheduler-tick
./scripts/smoke/run.sh pipelines-e2e
```

Live frontend probing (optional — requires `next dev` running):

```sh
cd theseus-codex && npm run dev -- -H 127.0.0.1 &
PUBLIC_BASE_URL=http://127.0.0.1:3000 ./scripts/smoke/run.sh frontend-routes
```

The harness writes one JSON per section to
`docs/verification/smoke/<timestamp>/<section>.json` plus a
`SUMMARY.json`.

## What each section catches

| Section | Catches |
| --- | --- |
| `frontend-routes` | A new SSR route 500s because it imports a deleted module; a page loses its default export; a route's body renders the Next.js error boundary instead of `<main>`. Static analysis runs unconditionally. Live HTTP probing runs when `PUBLIC_BASE_URL` is set. |
| `api-endpoints` | A FastAPI route references a column that the Prisma migration committed but the Alembic revision missed (the import path crashes on boot, or the handler 5xx's on first hit). SSE endpoints stop emitting frames. Operator endpoints lose their HMAC signature check. |
| `cli-help` | A Typer subcommand was registered but its handler raises on `--help` because of a top-level import error. A Typer app silently lost its registration (root help no longer advertises any subcommand). |
| `scheduler-tick` | A scheduler sub-loop's import fails at startup so the loop never runs. A new sub-loop name was added to `_LOOP_NAMES` but its runner crashes immediately. |
| `pipelines-e2e` | The three core pipelines (artifact → principle, algorithm DRAFT → ACTIVE → tick, synthesizer → memo → dispatch) can no longer be reached at all because a module was deleted or a model surface shifted. |

## Constraints the harness enforces on itself

* **Fixtures, never live data.** Per-run temp SQLite (no Postgres,
  no shared DB). External HTTP calls are mocked at the request
  layer (httpx-mock / respx) and never hit the network.
* **No mutation of the operator's working DB.** The harness wipes
  its temp file on exit; nothing leaks into `noosphere.db` or any
  Codex Postgres instance.
* **Fast.** Target: full run under 4 minutes on an M-series Mac.
  Any section that exceeds 30s emits a `perf_warning` in its JSON.
* **Structured failures.** Operators read the JSON, not the stderr.
  Every check carries `{name, ok, detail}`; failures carry enough
  context to reproduce.

## Adding a new section

When a new pipeline lands:

1. Add a new module `scripts/smoke/<my_section>.py` following the
   convention of the existing sections — module exposes
   `run(output_dir, **opts) -> dict`.
2. Wire it into `scripts/smoke/run.sh` (append to `ALL_SECTIONS` and
   the `case` block).
3. Add a row to the table above documenting what it catches.
4. Add a self-test in `tests/static/test_smoke_harness_itself.py`
   that plants a deliberate break inside the section's surface and
   asserts the smoke harness catches it.

The third step is the part that's easy to skip and easy to regret —
a smoke section without a self-test will, sooner or later, silently
stop catching the thing it was added to catch.

## Pre-sync integration

`scripts/sync-to-github.sh` runs the smoke harness before the push by
default. Skip with `--skip-smoke` (only for emergency code-only
pushes; the bypass prints a loud warning).

## CI integration

`.github/workflows/smoke.yml` runs the harness on every PR and posts
a structured summary as a PR comment. Any failure fails the PR check.
