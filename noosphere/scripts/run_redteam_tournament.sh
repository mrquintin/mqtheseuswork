#!/usr/bin/env bash
# Run the red-team tournament against the frozen v1 bench and archive
# the result. Designed for the recurring workflow at
# .github/workflows/redteam_tournament.yml; also runnable locally:
#
#   ./noosphere/scripts/run_redteam_tournament.sh
#
# Honours the same skip-when-key-missing contract as the replication
# harness — a configuration whose providers all lack API keys is
# logged and skipped rather than failing the run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BENCH_PATH="${REDTEAM_BENCH:-${REPO_ROOT}/benchmarks/redteam/v1/conclusion_bench.jsonl}"
ARCHIVE_DIR="${REDTEAM_ARCHIVE:-${REPO_ROOT}/noosphere_data/redteam_tournament/archive}"

mkdir -p "${ARCHIVE_DIR}"

cd "${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}/noosphere:${PYTHONPATH:-}"

python - <<'PY'
"""Driver: load the v1 bench, build a default configuration roster,
run the tournament, archive the JSON result.

Each configuration is content-addressable. Adding or changing a row
here is a real schema change — the archived envelope changes hash.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from noosphere.peer_review.providers import all_adapters, available_providers
from noosphere.peer_review.tournament import (
    DEFAULT_BENCH_PATH,
    ReviewerConfig,
    bench_sha256,
    load_bench,
    run_tournament,
    write_tournament_result,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("redteam_tournament")

bench_path = Path(os.environ.get("REDTEAM_BENCH", str(DEFAULT_BENCH_PATH)))
archive_dir = Path(os.environ["REDTEAM_ARCHIVE"])

bench = load_bench(bench_path)
log.info("loaded %d bench items from %s", len(bench), bench_path)

available = {a.name for a in available_providers()}
all_names = {a.name for a in all_adapters()}
log.info("available providers: %s (of %s)", sorted(available), sorted(all_names))

# Default configuration roster. Reuse-able, content-addressable; the
# leaderboard's top-of-page links each row back to this list.
roster_candidates: list[ReviewerConfig] = [
    ReviewerConfig(
        provider_mix=("anthropic", "openai", "gemini", "mistral_oss"),
        prompt_variant="default",
        temperature=0.2,
        seed=42,
        label="full-swarm",
        description="Every available frontier + open-weights provider, low-temperature.",
    ),
    ReviewerConfig(
        provider_mix=("anthropic", "openai"),
        prompt_variant="default",
        temperature=0.2,
        seed=42,
        label="frontier-pair",
        description="Closed-weights frontier providers only.",
    ),
    ReviewerConfig(
        provider_mix=("gemini", "mistral_oss"),
        prompt_variant="default",
        temperature=0.2,
        seed=42,
        label="diverse-pair",
        description="Different-vendor frontier + open-weights pair.",
    ),
    ReviewerConfig(
        provider_mix=("anthropic",),
        prompt_variant="default",
        temperature=0.7,
        seed=7,
        label="anthropic-creative",
        description="Single-provider, higher temperature; monoculture probe.",
    ),
]

# Skip configurations that have no available providers; the harness
# would mark them partial across the entire bench.
roster: list[ReviewerConfig] = []
for cfg in roster_candidates:
    if available and not (set(cfg.provider_mix) & available):
        log.warning("skipping config %s — no providers available", cfg.label)
        continue
    roster.append(cfg)

if not roster:
    log.error("no configurations have any available providers; nothing to run")
    raise SystemExit(0)

result = run_tournament(
    bench,
    roster,
    bench_path=bench_path,
    bench_hash=bench_sha256(bench_path),
)

out = write_tournament_result(result, archive_dir)
log.info("wrote %s", out)
print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
PY
