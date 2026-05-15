#!/usr/bin/env bash
#
# run_first_digest.sh — production cutover for the follow-digest pipeline.
#
# Round 18 prompt 32. Sends the firm's first real follow-digest cycle
# to the active subscriber list. The pipeline is intentionally split
# across two processes so neither component owns more than it should:
#
#   1. theseus-codex exports an INTAKE JSON of active subscribers plus
#      digest-eligible events (publications, revisions, retractions,
#      method-version transitions, calibration breaches). This step
#      generates the per-cycle ack tokens and stages DigestSend rows
#      in `status="pending"` so a crash mid-flight does not silently
#      drop sends.
#
#   2. noosphere.social.scheduler reads the intake, runs the pure
#      builder, and writes an OUTBOX JSON of rendered per-subscriber
#      digests (text + html + List-Unsubscribe headers).
#
#   3. theseus-codex re-ingests the outbox, hands each digest to the
#      existing sendMail transport (Resend / SMTP — both audited by
#      the firm; no third-party with non-auditable telemetry), records
#      the terminal delivery status on the staged DigestSend row, and
#      bumps Subscriber.lastSentAt. Bounces / blocks are written to
#      SubscriberBounce; the SUBSCRIBER_BOUNCE_PAUSE_THRESHOLD is
#      checked at the same point so a hard-bouncing address is paused
#      rather than spammed.
#
# This script is the run wrapper. It does not embed business logic.
#
# Usage:
#   noosphere/scripts/run_first_digest.sh \
#       [--dry-run] [--site-url URL] [--out-dir DIR]
#
# --dry-run is the default for safety on first invocation: the script
# generates the intake + outbox + metrics report but does not invoke
# the codex deliver endpoint. Pass --send to actually deliver.

set -euo pipefail

DRY_RUN=1
SITE_URL="${THESEUS_PUBLIC_SITE_URL:-https://theseuscodex.com}"
OUT_DIR=""
CODEX_BASE="${THESEUS_CODEX_BASE:-http://localhost:3000}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --send)        DRY_RUN=0; shift ;;
    --dry-run)     DRY_RUN=1; shift ;;
    --site-url)    SITE_URL="$2"; shift 2 ;;
    --out-dir)     OUT_DIR="$2"; shift 2 ;;
    --codex-base)  CODEX_BASE="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,40p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ -z "$OUT_DIR" ]]; then
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  OUT_DIR=".artifacts/digest/first_${TS}"
fi
mkdir -p "$OUT_DIR"

INTAKE="$OUT_DIR/intake.json"
OUTBOX="$OUT_DIR/outbox.json"
METRICS="$OUT_DIR/metrics.json"
LOG="$OUT_DIR/run.log"

echo "[run_first_digest] site=$SITE_URL out=$OUT_DIR dry_run=$DRY_RUN" | tee -a "$LOG"

# Step 1 — export intake from codex. The endpoint is admin-only and
# stages DigestSend rows in `pending`; if we exit before delivery, the
# next run can resume by filtering those rows.
echo "[run_first_digest] exporting intake from $CODEX_BASE" | tee -a "$LOG"
if ! curl -fsS -X POST \
     -H 'content-type: application/json' \
     -d "{\"siteUrl\":\"$SITE_URL\"}" \
     "$CODEX_BASE/api/ops/digest/intake" -o "$INTAKE" 2>>"$LOG"; then
  echo "[run_first_digest] intake export failed — see $LOG" >&2
  exit 1
fi

# Step 2 — run the pure builder. This is offline; the Python module
# does not touch the database and has no Anthropic / OpenAI calls.
echo "[run_first_digest] building per-subscriber digests" | tee -a "$LOG"
python -m noosphere.social.scheduler \
       --intake "$INTAKE" \
       --outbox "$OUTBOX" 2>&1 | tee -a "$LOG"

# Step 3 — capture metrics. Use jq when available; fall back to a
# minimal Python one-liner so the script runs on a bare CI image.
echo "[run_first_digest] writing metrics" | tee -a "$LOG"
python - "$INTAKE" "$OUTBOX" "$METRICS" <<'PYEOF'
import json
import sys
from datetime import datetime, timezone

intake_path, outbox_path, metrics_path = sys.argv[1:4]
intake = json.loads(open(intake_path, encoding="utf-8").read())
outbox = json.loads(open(outbox_path, encoding="utf-8").read())

subs = intake.get("subscribers", [])
events = intake.get("events", [])
digests = outbox.get("digests", [])
ack_links = sum(1 for d in digests if d.get("ack_url"))

metrics = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "site_url": intake.get("site_url", ""),
    "subscribers_total": len(subs),
    "subscribers_active": sum(1 for s in subs if s.get("status", "active") == "active"),
    "events_eligible": len(events),
    "digests_built": len(digests),
    "digests_with_ack_link": ack_links,
    "digests_without_ack_link": len(digests) - ack_links,
    # Delivered/bounced are filled in after the codex deliver call;
    # for --dry-run they stay at zero.
    "delivered": 0,
    "bounced": 0,
}
open(metrics_path, "w", encoding="utf-8").write(json.dumps(metrics, indent=2, sort_keys=True))
print(json.dumps(metrics, indent=2, sort_keys=True))
PYEOF

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[run_first_digest] dry-run complete; outbox staged at $OUTBOX" | tee -a "$LOG"
  echo "[run_first_digest] re-run with --send to actually deliver." | tee -a "$LOG"
  exit 0
fi

# Step 4 — deliver via codex. The deliver endpoint reads the staged
# DigestSend rows + the outbox, hands each rendered digest to sendMail,
# and writes terminal delivery status (delivered / bounced / blocked).
# Bounces auto-pause the subscriber when the threshold is reached.
echo "[run_first_digest] handing outbox to codex deliver endpoint" | tee -a "$LOG"
DELIVER_RESPONSE="$OUT_DIR/deliver_response.json"
if ! curl -fsS -X POST \
     -H 'content-type: application/json' \
     --data-binary "@$OUTBOX" \
     "$CODEX_BASE/api/ops/digest/deliver" -o "$DELIVER_RESPONSE" 2>>"$LOG"; then
  echo "[run_first_digest] deliver failed — see $LOG" >&2
  exit 1
fi

python - "$DELIVER_RESPONSE" "$METRICS" <<'PYEOF'
import json
import sys

resp = json.loads(open(sys.argv[1], encoding="utf-8").read())
metrics = json.loads(open(sys.argv[2], encoding="utf-8").read())
metrics["delivered"] = int(resp.get("delivered", 0))
metrics["bounced"] = int(resp.get("bounced", 0))
metrics["blocked"] = int(resp.get("blocked", 0))
open(sys.argv[2], "w", encoding="utf-8").write(json.dumps(metrics, indent=2, sort_keys=True))
print(json.dumps(metrics, indent=2, sort_keys=True))
PYEOF

echo "[run_first_digest] done. Metrics: $METRICS" | tee -a "$LOG"
