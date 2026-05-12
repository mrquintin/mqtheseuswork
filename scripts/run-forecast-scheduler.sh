#!/usr/bin/env bash
# Run the Forecasts scheduler.
#
# Modes:
#   loop        (default)  Standing loop. Runs forever, owns its own cadence.
#   once                   One tick through every sub-loop, then exits.
#   metric-scan            One pass of the decision-metric scan only.
#   status-only            Refresh forecasts_status.json without running ticks.
#
# Useful for local dev (`./scripts/run-forecast-scheduler.sh loop`), for
# cron-driven hosting (`./scripts/run-forecast-scheduler.sh once` every N min),
# and for health probes (`./scripts/run-forecast-scheduler.sh status-only`).

set -euo pipefail

MODE="${1:-loop}"
shift || true

case "$MODE" in
  loop)        exec python -m noosphere.forecasts.scheduler run "$@" ;;
  once|tick)   exec python -m noosphere.forecasts.scheduler tick "$@" ;;
  metric-scan) exec python -m noosphere.forecasts.scheduler metric-scan "$@" ;;
  status-only) exec python -m noosphere.forecasts.scheduler status-only "$@" ;;
  *)
    echo "usage: $0 {loop|once|metric-scan|status-only} [--loop NAME]..." >&2
    exit 2
    ;;
esac
