#!/usr/bin/env bash
# round18_smoke.sh
#
# Smoke-tests the public surfaces touched in the Round 18 prompt set.
# Each route must respond 200 and contain a hero phrase. The script does NOT
# start a dev server itself — point it at one with PUBLIC_BASE_URL (default
# http://127.0.0.1:3000).
#
# Usage:
#   PUBLIC_BASE_URL=http://127.0.0.1:3000 ./scripts/round18_smoke.sh
#
# Exit codes:
#   0  every route returned 200 with the expected hero phrase
#   1  one or more routes failed
#   2  base URL is unreachable

set -u

BASE="${PUBLIC_BASE_URL:-http://127.0.0.1:3000}"

if ! curl -sS -o /dev/null --max-time 5 "${BASE}/"; then
  echo "round18_smoke: base URL not reachable: ${BASE}" >&2
  echo "  start the dev server first (cd theseus-codex && npm run dev -- -H 127.0.0.1)" >&2
  exit 2
fi

# route<TAB>expected hero phrase
# - The Round-17 surfaces (calibration, /methodology/*) still need to work
#   after the Round-18 stabilization pass; failing on either is a regression.
# - The new Round-18 surfaces are added below.
ROUTES=(
  # Carry-over from Round 17 (must still be green after stabilization)
  "/calibration	Calibration scorecard"
  "/methodology/criteria	Five-criterion rubric"
  "/methodology/replicate	Replicate the firm"
  "/methodology/redteam	Red-team tournament"
  "/ask	Ask the firm"
  "/critiques	Critique hall of fame"
  "/privacy	Privacy & Data Retention"
  "/research/seasonal	Quarterly research reviews"

  # New / re-shaped in Round 18
  "/methodology	Methodology"
  "/methodology/benchmark/qh	Quintin Hypothesis"
  "/methodology/benchmark/qh/cross-model	Cross-model"
  "/methodology/contradiction_geometry	Contradiction geometry"
  "/about/reader-guide	Reader guide"
)

fails=0
for entry in "${ROUTES[@]}"; do
  route="${entry%%	*}"
  hero="${entry#*	}"
  url="${BASE}${route}"
  status="$(curl -sS -o /tmp/round18_smoke_body.html -w '%{http_code}' --max-time 30 "${url}")"
  if [[ "${status}" != "200" ]]; then
    echo "FAIL ${route}  (status=${status})"
    fails=$((fails + 1))
    continue
  fi
  if ! grep -qiF "${hero}" /tmp/round18_smoke_body.html; then
    echo "FAIL ${route}  (200 but missing hero phrase: '${hero}')"
    fails=$((fails + 1))
    continue
  fi
  echo "PASS ${route}  ('${hero}')"
done

rm -f /tmp/round18_smoke_body.html
if (( fails > 0 )); then
  echo
  echo "round18_smoke: ${fails} route(s) failed"
  exit 1
fi
echo
echo "round18_smoke: all ${#ROUTES[@]} routes ok"
