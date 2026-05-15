# Configuration

Round 17 consolidated the configuration surface that had drifted across the
monorepo. Per-prompt env-var lookups (`THESEUS_LOG_FILE`, `NOOSPHERE_*`,
per-feature thresholds, model defaults), inline magic numbers, and ad-hoc
`os.getenv` / `process.env.X` reads now route through two typed modules:

| Language   | Module                                       |
| ---------- | -------------------------------------------- |
| Python     | `noosphere/noosphere/core/config.py`         |
| TypeScript | `theseus-codex/src/lib/config.ts`            |

A single CI gate (`scripts/check_no_inline_env_reads.py`) enforces the
contract: only the central modules may read environment variables
directly.

---

## Loading order

Both languages share the same precedence model (highest precedence
wins):

```
config/defaults.yaml                  ←  committed defaults (lowest)
config/<THESEUS_ENV>.yaml             ←  per-environment overlay
process environment variables         ←  highest precedence
```

`THESEUS_ENV` selects the overlay file (`development`, `staging`,
`production`, `test`). When unset, Python defaults to `development`;
TypeScript falls back to `NODE_ENV`, then `development`.

YAML overlays live under `config/`. They are committed and reviewable.
**Secrets never go in YAML** — they remain environment-only.

The Python loader merges overlays through the `_layer_overlays` model
validator; the TypeScript loader builds an in-memory record from
`process.env` at access time. Nested mappings under
`thresholds:` are merged key-wise so you can override one threshold
without restating the whole tree.

---

## Required environment variables

The following variables are mandatory in production. Missing them
produces a `ConfigError` whose message names the variable and points at
this document.

| Variable             | Purpose                                                  |
| -------------------- | -------------------------------------------------------- |
| `DATABASE_URL`       | Production Postgres connection string. <a id="database"></a> |
| `ANTHROPIC_API_KEY`  | LLM inference key. <a id="llm-providers"></a> See also `OPENAI_API_KEY` for the auto-fallback path described below. |

The Python `Settings.effective_llm_provider()` helper picks the
provider whose key is present, regardless of the `THESEUS_LLM_PROVIDER`
preference, so a deploy with only `OPENAI_API_KEY` set still works
without a config tweak.

### Common optional variables

| Variable                  | Maps to                              |
| ------------------------- | ------------------------------------ |
| `THESEUS_ENV`             | `Settings.env`                       |
| `THESEUS_LOG_LEVEL`       | `Settings.log_level`                 |
| `THESEUS_LOG_FILE`        | `Settings.log_file`                  |
| `PUBLIC_SITE_ORIGIN`      | `Settings.public_site_origin` / `config.publicSiteOrigin` |
| `CURRENTS_API_URL`        | `Settings.currents_api_url` / `config.currentsApiUrl`     |
| `CURRENTS_CORS_ORIGINS`   | `Settings.currents_cors_origins` / `config.currentsCorsOrigins` (CSV) |
| `FORECASTS_*`             | live-trading guardrails — see `noosphere/noosphere/core/config.py` |

The `THESEUS_` prefix is the canonical namespace for settings unique to
Theseus. Bare names (e.g. `DATABASE_URL`, `ANTHROPIC_API_KEY`) are
preserved for compatibility with external tooling that expects those
exact spellings.

---

## Magic-number registry

Round 17 surfaced ~30 thresholds previously hidden as inline literals:
similarity cutoffs, severity multipliers, drift sigma values, sample-
size minima, retention TTLs, latency budgets. These are now centralised
under `Settings.thresholds` (Python) and `config.thresholds`
(TypeScript), grouped by domain:

- `currents` — engagement floors and per-cycle quotas for the
  X / news ingestor.
- `forecasts` — live-trading and budget guardrails.
- `calibration` — track-record discount parameters
  (STRATEGIC 05).
- `coherence` — similarity cutoffs and adversarial
  neighbourhood freshness.
- `retention` — TTLs for ephemeral caches and rate-limit windows.
- `latencyBudgetMs` (TS) / `latency_budget_ms` (PY) — end-to-end
  P95 budgets in milliseconds.

Every value carries its rationale next to its declaration in the source
module. **Centralising was a refactor; tuning is a separate workflow.**
Do not change a value here without an accompanying tuning prompt and
calibration record.

---

## Test-only overrides

Both languages expose a typed override path so tests do not have to
mutate process state.

**Python** (`Settings.with_overrides`, plus `Settings.patch` context
manager):

```python
from noosphere.core.config import Settings, get_settings

# One-shot copy
overridden = get_settings().with_overrides(currents_lookback_minutes=5)

# Transactional override of the singleton
with Settings.patch(currents_lookback_minutes=5) as patched:
    do_thing(patched)
```

**TypeScript** (`withConfigOverrides`, returns a dispose function):

```ts
import { config, withConfigOverrides } from "@/lib/config";

const restore = withConfigOverrides({ smtpHost: "localhost" });
try {
  await sendNotification();
} finally {
  restore();
}
```

Both override mechanisms preserve the immutability of the returned
config — assigning to a field on the override raises.

---

## CI gate

`scripts/check_no_inline_env_reads.py` enforces the rule that env
reads happen *only* in the central modules. Running it:

| Command                                                    | Effect                                       |
| ---------------------------------------------------------- | -------------------------------------------- |
| `python scripts/check_no_inline_env_reads.py`              | Fail on new direct env reads (gate mode).    |
| `python scripts/check_no_inline_env_reads.py --report`     | Print every direct env read still present.   |
| `python scripts/check_no_inline_env_reads.py --baseline`   | Rewrite the grandfathered baseline.          |
| `python scripts/check_no_inline_env_reads.py --strict`     | Fail on **any** direct env read (post-migration). |

The grandfathered set lives at
`scripts/no_inline_env_reads_baseline.json` as a JSON map of
`{path: read_count}`. The list is intended to **shrink**: when a file
is migrated to read from `Settings` / `config`, drop its baseline entry
and the gate will keep it that way.

### Migration checklist (per file)

1. Replace `os.getenv("FOO")` with `get_settings().foo` (Python) or
   `process.env.FOO` with `config.foo` (TypeScript).
2. If the value isn't yet a field on `Settings` / `AppConfig`, add it
   there with a default that preserves current behaviour.
3. If the call site needs a runtime override (typically tests), use
   `with_overrides` / `withConfigOverrides` rather than mutating
   `os.environ` / `process.env`.
4. Re-run the gate. If your file's baseline entry should change, run
   with `--baseline` and commit the diff.

---

## Allowlisted modules

The gate's allowlist (`PY_ALLOWED` / `TS_ALLOWED` in
`scripts/check_no_inline_env_reads.py`) currently contains:

- `noosphere/noosphere/core/config.py` — the Python settings module
  itself.
- `noosphere/noosphere/config.py` — legacy import shim that re-exports
  from the core module so existing callers keep working.
- `theseus-codex/src/lib/config.ts` — the TypeScript config module
  itself.

Adding a new module to either allowlist requires a one-line
justification in the source comment.

---

## Where to add a new field

1. Decide whether the value is a tunable (goes in `thresholds`) or a
   plain configuration knob (goes on `Settings` / `AppConfig`
   directly).
2. Add the field to the Python model (`noosphere/noosphere/core/config.py`)
   and, if the TypeScript surface needs it, the matching property on
   `AppConfig`.
3. Set a default in `config/defaults.yaml`. If the value needs
   per-environment differences, override in
   `config/<env>.yaml`. Never put secrets in YAML.
4. If it's a required env var, append to `REQUIRED_ENV_DOCS` so the
   missing-env error message points users back here.
5. If TypeScript needs it from `process.env`, append the var name to
   `KNOWN_ENV_VARS` in `theseus-codex/src/lib/config.ts`.
6. Update the relevant test (`noosphere/tests/test_config.py`,
   `theseus-codex/src/__tests__/config.test.ts`).
