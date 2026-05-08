#!/usr/bin/env bash
# round17_smoke.sh
#
# Smoke-tests the public surfaces added/touched in the round-17 prompt set.
# Each route must respond 200 and contain a hero phrase. The script does NOT
# start a dev server itself — point it at one with PUBLIC_BASE_URL (default
# http://127.0.0.1:3000).
#
# Usage:
#   PUBLIC_BASE_URL=http://127.0.0.1:3000 ./scripts/round17_smoke.sh
#
# Exit codes:
#   0  every route returned 200 with the expected hero phrase
#   1  one or more routes failed
#   2  base URL is unreachable

set -u

BASE="${PUBLIC_BASE_URL:-http://127.0.0.1:3000}"

# Confirm the host is up before iterating.
if ! curl -sS -o /dev/null --max-time 5 "${BASE}/"; then
  echo "round17_smoke: base URL not reachable: ${BASE}" >&2
  echo "  start the dev server first (cd theseus-codex && npm run dev -- -H 127.0.0.1)" >&2
  exit 2
fi

# route<TAB>expected hero phrase
ROUTES=(
  "/calibration	Calibration scorecard"
  "/methodology/criteria	Five-criterion rubric"
  "/methodology/replicate	Replicate the firm"
  "/methodology/redteam	Red-team tournament"
  "/ask	Ask the firm"
  "/critiques	Critique hall of fame"
  "/privacy	Privacy & Data Retention"
  "/research/seasonal	Quarterly research reviews"
)

fails=0
for entry in "${ROUTES[@]}"; do
  route="${entry%%	*}"
  hero="${entry#*	}"
  url="${BASE}${route}"
  body="$(curl -sS -o /tmp/round17_smoke_body.html -w '%{http_code}' --max-time 30 "${url}")"
  status="${body}"
  if [[ "${status}" != "200" ]]; then
    echo "FAIL ${route}  (status=${status})"
    fails=$((fails + 1))
    continue
  fi
  if ! grep -qF "${hero}" /tmp/round17_smoke_body.html; then
    echo "FAIL ${route}  (200 but missing hero phrase: '${hero}')"
    fails=$((fails + 1))
    continue
  fi
  echo "PASS ${route}  ('${hero}')"
done

rm -f /tmp/round17_smoke_body.html
if (( fails > 0 )); then
  echo
  echo "round17_smoke: ${fails} route(s) failed"
  exit 1
fi
echo
echo "round17_smoke: all ${#ROUTES[@]} routes ok"
