#!/usr/bin/env bash
#
# run_resolution_backfill.sh — operational harness for Round 17 prompt 13.
#
# Drives the forecast resolution backfill across Polymarket + Kalshi end to
# end, the way an operator (or a scheduled job) would:
#
#   A. Pre-flight  — confirm venue keys, a clean import, the budget cap, a
#                    reachable store with the forecast schema. A failed gate
#                    STOPS the run; nothing is written.
#   B. Dry-run     — backfill(dry_run=True); report what *would* change to
#                    docs/runs/resolution_backfill_<stamp>_dryrun.md
#   C. Apply       — backfill(dry_run=False); capture write counts, override
#                    conflicts, discrepancies. Every ResolutionMismatch row is
#                    an entry in the founder triage queue.
#   D. Recompute   — public calibration manifest (prompt 12), per-method track
#                    records (prompt 02), recalibration model (prompt 14).
#   E. Verify      — spot-check >=10 random newly-resolved forecasts against the
#                    venue. Discrepancy rate over the threshold halts automation.
#   F. Publish     — append a summary to docs/runs/resolution_backfill_<stamp>.md
#
# The backfill driver itself lives in
# noosphere/noosphere/forecasts/resolution_backfill.py and is the only writer
# of ForecastResolution rows out of band of the live poller. This script does
# not re-implement any of its logic — it is the run wrapper, the report
# generator, and the pre-flight gate.
#
# Usage:
#   run_resolution_backfill.sh [options]
#
# Options:
#   --venue {all,polymarket,kalshi}   Venue filter (default: all)
#   --since ISO8601                   Only predictions created at/after this
#   --org ORG_ID                      Restrict to one tenant
#   --limit N                         Max predictions to inspect (default: 1000)
#   --dry-run-only                    Stop after stage B (no writes)
#   --allow-degraded                  Proceed even if a venue is unconfigured;
#                                     the run is restricted to configured venues
#   --discrepancy-threshold FLOAT     Verify halt threshold (default: 0.05)
#   -h, --help                        Show this help
#
# Exit codes:
#   0  completed (or dry-run-only completed)
#   2  bad usage
#   3  pre-flight GATED — run did not start; reports document the gate
#   5  verify discrepancy over threshold — automation halted, founder review
#
set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOOSPHERE_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$NOOSPHERE_DIR")"
RUNS_DIR="$REPO_ROOT/docs/runs"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DRYRUN_REPORT="$RUNS_DIR/resolution_backfill_${STAMP}_dryrun.md"
REPORT="$RUNS_DIR/resolution_backfill_${STAMP}.md"
PREFLIGHT_JSON="$(mktemp -t resbackfill_preflight.XXXXXX)"
DRIVER="${TMPDIR:-/tmp}/resolution_backfill_driver_$$.py"
trap 'rm -f "$DRIVER" "$PREFLIGHT_JSON"' EXIT

# ── Defaults / args ────────────────────────────────────────────────────
VENUE="all"
SINCE=""
ORG=""
LIMIT="1000"
DRY_RUN_ONLY="0"
ALLOW_DEGRADED="0"
DISCREPANCY_THRESHOLD="0.05"

usage() { sed -n '2,46p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --venue) VENUE="${2:-}"; shift 2 ;;
    --since) SINCE="${2:-}"; shift 2 ;;
    --org) ORG="${2:-}"; shift 2 ;;
    --limit) LIMIT="${2:-}"; shift 2 ;;
    --dry-run-only) DRY_RUN_ONLY="1"; shift ;;
    --allow-degraded) ALLOW_DEGRADED="1"; shift ;;
    --discrepancy-threshold) DISCREPANCY_THRESHOLD="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "run_resolution_backfill: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# ── Environment ────────────────────────────────────────────────────────
# Load .env files so venue keys / DATABASE_URL surface to the pre-flight
# check the same way they would for a scheduled job. Repo-root first, then
# the noosphere package dir; later files do not clobber earlier exports
# already set in the real environment.
for envfile in "$REPO_ROOT/.env" "$NOOSPHERE_DIR/.env"; do
  if [ -f "$envfile" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$envfile"
    set +a
  fi
done

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  PYTHON="python"
fi
export PYTHONPATH="$NOOSPHERE_DIR:${PYTHONPATH:-}"

mkdir -p "$RUNS_DIR"

# ── Embedded Python driver ─────────────────────────────────────────────
# Kept in one place: this script writes it to a temp file at run time and
# invokes it per stage. It only orchestrates library calls — all backfill,
# scoring, manifest and recalibration logic lives in the noosphere package.
cat > "$DRIVER" <<'PYEOF'
"""Run-time driver for run_resolution_backfill.sh. Not a committed module."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import traceback
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_db_url() -> tuple[str, str]:
    for key in (
        "DATABASE_URL",
        "THESEUS_DATABASE_URL",
        "THESEUS_CODEX_DATABASE_URL",
        "CODEX_DATABASE_URL",
        "DIRECT_URL",
    ):
        val = os.environ.get(key, "").strip()
        if val:
            return val, key
    try:
        from noosphere.config import get_settings

        return get_settings().database_url, "noosphere.config.default"
    except Exception as exc:  # pragma: no cover - config import guard
        return "", f"unresolved ({type(exc).__name__}: {exc})"


def _scheme(url: str) -> str:
    return url.split("://", 1)[0] if "://" in url else (url or "<none>")


# ── Pre-flight ─────────────────────────────────────────────────────────


def preflight() -> dict:
    checks: dict = {}
    reasons: list[str] = []

    try:
        import noosphere.forecasts.resolution_backfill as _rb  # noqa: F401

        checks["import_resolution_backfill"] = True
    except Exception as exc:
        checks["import_resolution_backfill"] = False
        reasons.append(
            f"resolution_backfill import failed: {type(exc).__name__}: {exc}"
        )

    # Polymarket Gamma is a keyless public API; "present" means the config
    # loads and a base URL is set.
    try:
        from noosphere.forecasts.config import PolymarketConfig

        pc = PolymarketConfig.from_env()
        checks["polymarket_config"] = bool(pc.gamma_base)
        checks["polymarket_gamma_base"] = pc.gamma_base
        if not pc.gamma_base:
            reasons.append("Polymarket Gamma base URL is empty")
    except Exception as exc:
        checks["polymarket_config"] = False
        reasons.append(
            f"PolymarketConfig.from_env failed: {type(exc).__name__}: {exc}"
        )

    # Kalshi requires an API key id + private key PEM.
    try:
        from noosphere.forecasts.config import KalshiConfig

        kc = KalshiConfig.from_env()
        checks["kalshi_configured"] = bool(kc.is_configured)
        checks["kalshi_api_base"] = kc.api_base
        if not kc.is_configured:
            reasons.append(
                "Kalshi keys absent (KALSHI_API_KEY_ID / "
                "KALSHI_API_PRIVATE_KEY not set)"
            )
    except Exception as exc:
        checks["kalshi_configured"] = False
        reasons.append(
            f"KalshiConfig.from_env failed: {type(exc).__name__}: {exc}"
        )

    # Budget cap.
    try:
        from noosphere.forecasts.budget import (
            DEFAULT_BUDGET_PATH,
            DEFAULT_COMPLETION_TOKENS_HOUR,
            DEFAULT_PROMPT_TOKENS_HOUR,
            PersistentHourlyBudgetGuard,
        )

        checks["budget_prompt_tokens_hour"] = DEFAULT_PROMPT_TOKENS_HOUR
        checks["budget_completion_tokens_hour"] = DEFAULT_COMPLETION_TOKENS_HOUR
        checks["budget_path"] = str(DEFAULT_BUDGET_PATH)
        checks["budget_cap_set"] = (
            DEFAULT_PROMPT_TOKENS_HOUR > 0 and DEFAULT_COMPLETION_TOKENS_HOUR > 0
        )
        if not checks["budget_cap_set"]:
            reasons.append("Budget cap is not a positive hourly envelope")
        try:
            guard = PersistentHourlyBudgetGuard()
            guard.path.parent.mkdir(parents=True, exist_ok=True)
            guard.save()
            checks["budget_path_writable"] = True
        except Exception as exc:
            # Not fatal: the driver falls back to running without a
            # persistent guard on machines where the path is unwritable.
            checks["budget_path_writable"] = False
            checks["budget_path_note"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        checks["budget_cap_set"] = False
        reasons.append(f"budget module failed: {type(exc).__name__}: {exc}")

    # Store + forecast schema.
    db_url, db_src = _resolve_db_url()
    checks["database_url_source"] = db_src
    checks["database_url_scheme"] = _scheme(db_url)
    store_ok = False
    schema_ok = False
    pending_estimate = None
    try:
        from noosphere.store import Store

        store = Store.from_database_url(db_url)
        store_ok = True
        try:
            store.list_published_predictions_for_backfill(limit=1)
            schema_ok = True
            try:
                pending_estimate = len(
                    store.list_published_predictions_for_backfill(limit=1_000_000)
                )
            except Exception:
                pending_estimate = None
        except Exception as exc:
            reasons.append(
                f"forecast schema not queryable: {type(exc).__name__}: {exc}"
            )
    except Exception as exc:
        reasons.append(f"store unreachable: {type(exc).__name__}: {exc}")
    checks["store_reachable"] = store_ok
    checks["forecast_schema_present"] = schema_ok
    checks["pending_prediction_estimate"] = pending_estimate

    allow_degraded = os.environ.get("RB_ALLOW_DEGRADED", "0") == "1"
    venues_ok = checks.get("polymarket_config") and checks.get("kalshi_configured")
    hard_fail = (
        not checks.get("import_resolution_backfill")
        or not store_ok
        or not schema_ok
        or not checks.get("budget_cap_set")
    )
    if hard_fail:
        verdict = "GATED"
    elif not venues_ok and not allow_degraded:
        verdict = "GATED"
    elif not venues_ok and allow_degraded:
        verdict = "DEGRADED"
    else:
        verdict = "PASS"

    return {
        "verdict": verdict,
        "checks": checks,
        "reasons": reasons,
        "allow_degraded": allow_degraded,
        "generated_at": _stamp(),
    }


# ── Markdown helpers ───────────────────────────────────────────────────


def _yn(value) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value)


def _preflight_md(pf: dict) -> str:
    c = pf["checks"]
    lines = [
        "## A. Pre-flight",
        "",
        f"- verdict: **{pf['verdict']}**",
        f"- resolution_backfill imports cleanly: "
        f"{_yn(c.get('import_resolution_backfill'))}",
        f"- Polymarket config present: {_yn(c.get('polymarket_config'))} "
        f"(gamma_base={c.get('polymarket_gamma_base', '—')})",
        f"- Kalshi keys present: {_yn(c.get('kalshi_configured'))} "
        f"(api_base={c.get('kalshi_api_base', '—')})",
        f"- budget cap set: {_yn(c.get('budget_cap_set'))} "
        f"(prompt={c.get('budget_prompt_tokens_hour', '—')}/h, "
        f"completion={c.get('budget_completion_tokens_hour', '—')}/h, "
        f"path={c.get('budget_path', '—')}, "
        f"writable={_yn(c.get('budget_path_writable'))})",
        f"- store reachable: {_yn(c.get('store_reachable'))} "
        f"(url source={c.get('database_url_source', '—')}, "
        f"scheme={c.get('database_url_scheme', '—')})",
        f"- forecast schema present: {_yn(c.get('forecast_schema_present'))}",
        f"- pending-prediction estimate: "
        f"{c.get('pending_prediction_estimate', '—')}",
    ]
    if pf["reasons"]:
        lines.append("")
        lines.append("Gate reasons:")
        for reason in pf["reasons"]:
            lines.append(f"- {reason}")
    return "\n".join(lines)


def _header(stamp: str, kind: str) -> str:
    return "\n".join(
        [
            f"# Resolution backfill — {kind}",
            "",
            f"- run stamp (UTC): `{stamp}`",
            f"- generated_at: {_stamp()}",
            "- driver: `noosphere/scripts/run_resolution_backfill.sh`",
            "- backfill module: "
            "`noosphere/noosphere/forecasts/resolution_backfill.py`",
            "",
        ]
    )


# ── report-gated ───────────────────────────────────────────────────────


def cmd_report_gated(args: argparse.Namespace) -> int:
    with open(args.preflight_json, encoding="utf-8") as fh:
        pf = json.load(fh)

    gated_note = "\n".join(
        [
            "## Run not started — pre-flight GATE",
            "",
            "The pre-flight stage did not pass, so the harness stopped "
            "before stage B. **No venues were queried and no rows were "
            "written.** This is the harness behaving as designed: the "
            "pre-flight is a gate, not a warning.",
            "",
            "Re-run once the gate reasons above are resolved. The backfill is "
            "idempotent and resumable, so a gated run costs nothing — the next "
            "run picks up the full pending set.",
            "",
        ]
    )

    dry_body = "\n".join(
        [
            _header(args.stamp, "dry-run"),
            _preflight_md(pf),
            "",
            "## B. Dry-run",
            "",
            "Not executed — pre-flight GATED (see above). A dry-run still "
            "needs a reachable store and the forecast schema to enumerate "
            "the pending prediction set.",
            "",
            gated_note,
        ]
    )
    with open(args.dryrun_report, "w", encoding="utf-8") as fh:
        fh.write(dry_body)

    main_body = "\n".join(
        [
            _header(args.stamp, "apply"),
            _preflight_md(pf),
            "",
            gated_note,
            "## C–F. Apply / Recompute / Verify / Publish",
            "",
            "Not executed — pre-flight GATED. Nothing was written to the "
            "store, no manifest was recomputed, and the public calibration "
            "scorecard is unchanged.",
            "",
        ]
    )
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(main_body)
    return 0


# ── shared run setup ───────────────────────────────────────────────────


def _open_store():
    from noosphere.store import Store

    db_url, _src = _resolve_db_url()
    return Store.from_database_url(db_url)


def _run_kwargs(args: argparse.Namespace) -> dict:
    kwargs: dict = {
        "venue": args.venue,
        "limit": int(args.limit),
    }
    if args.org:
        kwargs["organization_id"] = args.org
    if args.since:
        kwargs["since"] = datetime.fromisoformat(
            args.since.replace("Z", "+00:00")
        )
    return kwargs


def _summary_table(summary) -> str:
    rows = summary.to_dict()
    return "\n".join(
        [
            "| metric | count |",
            "| --- | --- |",
            f"| rows inspected | {len(rows['rows'])} |",
            f"| resolutions written | {len(rows['written_predictions'])} |",
            f"| founder overrides applied | {len(rows['overrides_applied'])} |",
            f"| mismatches logged (to triage) | {len(rows['mismatches_logged'])} |",
            f"| revisions logged | {len(rows['revisions_logged'])} |",
            f"| skipped — still open | {rows['skipped_still_open']} |",
            f"| skipped — already resolved | {rows['skipped_already_resolved']} |",
            f"| skipped — unknown market | {rows['skipped_unknown_market']} |",
            f"| errors | {rows['errors']} |",
            f"| budget exhausted | {_yn(rows['budget_exhausted'])} |",
        ]
    )


def _intended_breakdown(summary) -> str:
    counts: dict[str, int] = {}
    for row in summary.rows:
        key = row.intended_action or row.action
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return "_No predictions in the pending set._"
    lines = ["| intended action | count |", "| --- | --- |"]
    for key in sorted(counts):
        lines.append(f"| {key} | {counts[key]} |")
    return "\n".join(lines)


# ── dryrun ─────────────────────────────────────────────────────────────


def cmd_dryrun(args: argparse.Namespace) -> int:
    from noosphere.forecasts.resolution_backfill import run_backfill

    with open(args.preflight_json, encoding="utf-8") as fh:
        pf = json.load(fh)

    store = _open_store()
    summary = run_backfill(store, dry_run=True, **_run_kwargs(args))

    body = [
        _header(args.stamp, "dry-run"),
        _preflight_md(pf),
        "",
        "## B. Dry-run",
        "",
        f"`backfill(dry_run=True, venue={args.venue!r}, limit={args.limit})` "
        "— no rows written, every prediction reports the action it *would* "
        "take.",
        "",
        "### What would change",
        "",
        _summary_table(summary),
        "",
        "### Intended-action breakdown",
        "",
        _intended_breakdown(summary),
        "",
        "Run the harness without `--dry-run-only` to apply.",
        "",
    ]
    with open(args.dryrun_report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body))
    print(
        f"dry-run: inspected {len(summary.rows)} prediction(s); "
        f"would write {len(summary.written_predictions)}, "
        f"override {len(summary.overrides_applied)}, "
        f"mismatch {len(summary.mismatches_logged)}, "
        f"revise {len(summary.revisions_logged)}"
    )
    return 0


# ── apply (C + D + E + F) ──────────────────────────────────────────────


def _recompute_recalibration(store) -> dict:
    """Best-effort recalibration recompute (prompt 14).

    Postgres-only: it queries resolved binary predictions per tenant and
    refits the per-domain isotonic model. On a store without the
    ``CalibrationModel`` table (e.g. local SQLite) it records a skip
    rather than raising — the backfill commit is never poisoned by a
    recompute failure.
    """
    out: dict = {"attempted": True, "fitted_domains": 0, "tenants": 0}
    try:
        from noosphere.coherence.recalibration import (
            ResolvedRow,
            fit_and_persist_per_domain,
        )
    except Exception as exc:
        return {"attempted": False, "skipped": f"import: {type(exc).__name__}: {exc}"}

    engine = getattr(store, "engine", None)
    if engine is None:
        return {"attempted": False, "skipped": "store has no engine"}
    try:
        raw = engine.raw_connection()
    except Exception as exc:
        return {"attempted": False, "skipped": f"raw_connection: {exc}"}
    try:
        cur = raw.cursor()
        try:
            cur.execute(
                'SELECT fp."organizationId", fm.category, fp."probabilityYes", '
                '       fr."marketOutcome", fr."resolvedAt", fp.id '
                '  FROM "ForecastPrediction" fp '
                '  JOIN "ForecastMarket" fm ON fm.id = fp."marketId" '
                '  JOIN "ForecastResolution" fr ON fr."predictionId" = fp.id '
                ' WHERE fp.status = %s '
                '   AND fr."marketOutcome" IN (%s, %s)',
                ("PUBLISHED", "YES", "NO"),
            )
            fetched = cur.fetchall()
        finally:
            cur.close()
    except Exception as exc:
        try:
            raw.close()
        except Exception:
            pass
        return {"attempted": False, "skipped": f"query: {type(exc).__name__}: {exc}"}

    by_org: dict[str, list] = {}
    for row in fetched:
        org = str(row[0])
        try:
            prob = float(row[2])
        except (TypeError, ValueError):
            continue
        outcome = 1 if str(row[3]) == "YES" else 0
        resolved_at = row[4]
        if not isinstance(resolved_at, datetime):
            resolved_at = _utc_now()
        by_org.setdefault(org, []).append(
            ResolvedRow(
                prediction_id=str(row[5]),
                domain=str(row[1] or ""),
                probability_yes=prob,
                outcome=outcome,
                resolved_at=resolved_at,
            )
        )
    try:
        for org, rows in by_org.items():
            cur = raw.cursor()
            try:
                results = fit_and_persist_per_domain(
                    cur, rows, organization_id=org
                )
            finally:
                cur.close()
            out["tenants"] += 1
            out["fitted_domains"] += len(results)
        raw.commit()
    except Exception as exc:
        try:
            raw.rollback()
        except Exception:
            pass
        out = {"attempted": True, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            raw.close()
        except Exception:
            pass
    return out


def _read_published_manifest() -> dict | None:
    try:
        from noosphere.evaluation.public_calibration import default_manifest_path

        path = default_manifest_path()
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _headline_brier(manifest: dict | None):
    if not manifest:
        return None
    for window in manifest.get("aggregate_brier", []):
        if window.get("label") == "all-time":
            return window.get("mean_brier")
    return None


def _verify_spot_check(store, summary, threshold: float) -> dict:
    """Stage E: re-query the venue for up to 10 random newly-resolved
    forecasts and compare the venue outcome to the resolution row the
    backfill just wrote. A discrepancy rate over ``threshold`` is the
    halt-automation signal."""
    import asyncio

    from noosphere.forecasts.resolution_backfill import _resolve_client

    written = list(summary.written_predictions)
    if not written:
        return {"sampled": 0, "discrepancies": 0, "rate": 0.0, "halt": False,
                "details": []}
    rng = random.Random(0xC0FFEE)
    sample = rng.sample(written, min(10, len(written)))

    async def _check() -> list[dict]:
        close_clients: list = []
        details: list[dict] = []
        try:
            for pid in sample:
                resolution = store.get_forecast_resolution(pid)
                if resolution is None:
                    details.append({"prediction_id": pid, "status": "no_row"})
                    continue
                # find the market behind this prediction
                pred_rows = store.list_published_predictions_for_backfill(
                    limit=1_000_000
                )
                market = None
                for pred in pred_rows:
                    if pred.id == pid:
                        market = store.get_forecast_market(pred.market_id)
                        break
                if market is None:
                    details.append({"prediction_id": pid, "status": "no_market"})
                    continue
                client = await _resolve_client(
                    market.source,
                    poly_client=None,
                    kalshi=None,
                    close_clients=close_clients,
                )
                if client is None:
                    details.append(
                        {"prediction_id": pid, "status": "venue_unconfigured"}
                    )
                    continue
                record = await client.fetch_resolution(market.external_id)
                venue_outcome = getattr(record, "outcome", None)
                recorded = (
                    resolution.market_outcome.value
                    if hasattr(resolution.market_outcome, "value")
                    else str(resolution.market_outcome)
                )
                match = venue_outcome == recorded or (
                    resolution.source == "OVERRIDE"
                )
                details.append(
                    {
                        "prediction_id": pid,
                        "venue_outcome": venue_outcome,
                        "recorded_outcome": recorded,
                        "source": resolution.source,
                        "match": match,
                    }
                )
        finally:
            for client in close_clients:
                try:
                    await client.aclose()
                except Exception:
                    pass
        return details

    details = asyncio.run(_check())
    checkable = [d for d in details if "match" in d]
    discrepancies = sum(1 for d in checkable if not d["match"])
    rate = discrepancies / len(checkable) if checkable else 0.0
    return {
        "sampled": len(sample),
        "checkable": len(checkable),
        "discrepancies": discrepancies,
        "rate": rate,
        "halt": rate > threshold,
        "details": details,
    }


def cmd_apply(args: argparse.Namespace) -> int:
    from noosphere.forecasts.resolution_backfill import run_backfill

    with open(args.preflight_json, encoding="utf-8") as fh:
        pf = json.load(fh)

    store = _open_store()
    threshold = float(args.discrepancy_threshold)

    # ── C. Apply ──
    summary = run_backfill(store, dry_run=False, **_run_kwargs(args))

    # Founder triage queue: every ResolutionMismatch row is, by
    # construction, an unreviewed entry. Surface the queue depth.
    try:
        triage = store.list_resolution_mismatches(unreviewed_only=True, limit=10_000)
    except Exception:
        triage = []
    triage_by_kind: dict[str, int] = {}
    for row in triage:
        triage_by_kind[row.kind] = triage_by_kind.get(row.kind, 0) + 1

    # ── D. Recompute ──
    # The public calibration manifest (prompt 12) and per-method track
    # records (prompt 02) are refreshed by the backfill driver's own
    # recompute hook. The recalibration model (prompt 14) is not part of
    # that hook, so the harness drives it here.
    recalibration = _recompute_recalibration(store)
    manifest = _read_published_manifest()
    headline = _headline_brier(manifest)

    revalidate: dict = {}
    try:
        from noosphere.evaluation.public_calibration import revalidate_public_page

        revalidate = revalidate_public_page()
    except Exception as exc:
        revalidate = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # ── E. Verify ──
    verify = _verify_spot_check(store, summary, threshold)

    # ── prior internal estimate ──
    prior = os.environ.get("THESEUS_PRIOR_BRIER_ESTIMATE", "").strip()
    if not prior:
        prior_path = os.path.join(
            os.path.dirname(args.report), ".prior_brier_estimate"
        )
        if os.path.exists(prior_path):
            with open(prior_path, encoding="utf-8") as fh:
                prior = fh.read().strip()

    # ── report body (C + D + E) ──
    body = [
        _header(args.stamp, "apply"),
        _preflight_md(pf),
        "",
        "## C. Apply",
        "",
        f"`backfill(dry_run=False, venue={args.venue!r}, limit={args.limit})` "
        "— wrote against venues "
        f"{sorted(summary.venues) if summary.venues else '[]'}.",
        "",
        _summary_table(summary),
        "",
        "### Founder triage queue",
        "",
        f"Unreviewed `ResolutionMismatch` rows: **{len(triage)}**",
        "",
    ]
    if triage_by_kind:
        body.append("| kind | count |")
        body.append("| --- | --- |")
        for kind in sorted(triage_by_kind):
            body.append(f"| {kind} | {triage_by_kind[kind]} |")
    else:
        body.append("_Queue is empty — no mismatches this run._")
    body += [
        "",
        "Every row above is an entry in the founder triage queue "
        "(`store.list_resolution_mismatches(unreviewed_only=True)`); none "
        "are auto-resolved.",
        "",
        "## D. Recompute",
        "",
        f"- public calibration manifest + per-method track records: "
        f"recompute hook fired = {_yn(summary.recompute_triggered)}",
        f"- recalibration model (prompt 14): {json.dumps(recalibration)}",
        f"- static revalidation of `/calibration`: {json.dumps(revalidate)}",
        "",
        "## E. Verify",
        "",
        f"Spot-checked {verify['sampled']} random newly-resolved forecast(s) "
        f"against the venue; {verify.get('checkable', 0)} were venue-checkable.",
        "",
        f"- discrepancies: {verify['discrepancies']}",
        f"- discrepancy rate: {verify['rate']:.3f} "
        f"(threshold {threshold:.3f})",
        f"- halt automation: {_yn(verify['halt'])}",
        "",
    ]
    if verify["details"]:
        body.append("| prediction | venue | recorded | source | match |")
        body.append("| --- | --- | --- | --- | --- |")
        for d in verify["details"]:
            body.append(
                f"| {d.get('prediction_id', '—')} "
                f"| {d.get('venue_outcome', d.get('status', '—'))} "
                f"| {d.get('recorded_outcome', '—')} "
                f"| {d.get('source', '—')} "
                f"| {_yn(d.get('match', '—'))} |"
            )
    if verify["halt"]:
        body += [
            "",
            "> **Automation halted.** Discrepancy rate exceeds the "
            "threshold. Founder review required before the next run.",
        ]
    body.append("")

    # ── F. Publish summary ──
    body += [
        "## F. Publish summary",
        "",
        f"- resolutions written: **{len(summary.written_predictions)}**",
        f"- founder overrides triggered: "
        f"**{len(summary.overrides_applied)}**",
        f"- mismatches sent to triage: **{len(summary.mismatches_logged)}** "
        f"this run (queue depth {len(triage)})",
        f"- revisions logged (no silent overwrite): "
        f"**{len(summary.revisions_logged)}**",
        f"- new headline calibration number (all-time Brier): "
        f"**{headline if headline is not None else '— (manifest not on disk)'}**",
        f"- resolution_set_hash: "
        f"`{manifest.get('resolution_set_hash') if manifest else '—'}`",
        f"- prior internal estimate: "
        f"{prior if prior else '— (none on record; this is the first published number)'}",
        "",
    ]
    if headline is not None and prior:
        try:
            delta = float(headline) - float(prior)
            body.append(
                f"- delta vs prior internal estimate: {delta:+.4f}"
            )
            body.append("")
        except ValueError:
            pass
    if summary.budget_exhausted:
        body += [
            "> **Partial completion.** The hourly API budget was exhausted "
            "mid-run. The rows already written are committed; re-run the "
            "harness to resume from where this run stopped.",
            "",
        ]

    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body))

    print(
        f"apply: wrote {len(summary.written_predictions)} resolution(s), "
        f"{len(summary.overrides_applied)} override(s), "
        f"{len(summary.mismatches_logged)} mismatch(es) to triage, "
        f"{len(summary.revisions_logged)} revision(s); "
        f"headline Brier={headline}; verify halt={verify['halt']}"
    )
    return 5 if verify["halt"] else 0


# ── main ───────────────────────────────────────────────────────────────


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="resolution_backfill_driver")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pre = sub.add_parser("preflight")
    p_pre.add_argument("--json-out", required=True)

    p_gated = sub.add_parser("report-gated")
    p_gated.add_argument("--preflight-json", required=True)
    p_gated.add_argument("--dryrun-report", required=True)
    p_gated.add_argument("--report", required=True)
    p_gated.add_argument("--stamp", required=True)

    common = dict(
        venue="all", since="", org="", limit="1000",
        discrepancy_threshold="0.05",
    )
    for name in ("dryrun", "apply"):
        sp = sub.add_parser(name)
        sp.add_argument("--preflight-json", required=True)
        sp.add_argument("--stamp", required=True)
        sp.add_argument("--venue", default=common["venue"])
        sp.add_argument("--since", default=common["since"])
        sp.add_argument("--org", default=common["org"])
        sp.add_argument("--limit", default=common["limit"])
        sp.add_argument(
            "--discrepancy-threshold",
            default=common["discrepancy_threshold"],
        )
        if name == "dryrun":
            sp.add_argument("--dryrun-report", required=True)
        else:
            sp.add_argument("--report", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "preflight":
        pf = preflight()
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(pf, fh, indent=2, default=str)
        print(f"VERDICT={pf['verdict']}")
        for reason in pf["reasons"]:
            print(f"  - {reason}")
        if pf["verdict"] == "GATED":
            return 3
        return 0
    if args.cmd == "report-gated":
        return cmd_report_gated(args)
    if args.cmd == "dryrun":
        return cmd_dryrun(args)
    if args.cmd == "apply":
        return cmd_apply(args)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception:  # pragma: no cover - surfaces tracebacks to the shell
        traceback.print_exc()
        sys.exit(1)
PYEOF

# ── Stage A: pre-flight ────────────────────────────────────────────────
echo "==> [A] pre-flight"
export RB_ALLOW_DEGRADED="$ALLOW_DEGRADED"
set +e
"$PYTHON" "$DRIVER" preflight --json-out "$PREFLIGHT_JSON"
PF_RC=$?
set -e

if [ "$PF_RC" -eq 3 ]; then
  echo "==> pre-flight GATED — writing reports, not starting the run"
  "$PYTHON" "$DRIVER" report-gated \
    --preflight-json "$PREFLIGHT_JSON" \
    --dryrun-report "$DRYRUN_REPORT" \
    --report "$REPORT" \
    --stamp "$STAMP"
  echo "    dry-run report: $DRYRUN_REPORT"
  echo "    run report:     $REPORT"
  exit 3
elif [ "$PF_RC" -ne 0 ]; then
  echo "run_resolution_backfill: pre-flight driver failed (rc=$PF_RC)" >&2
  exit "$PF_RC"
fi

# ── Stage B: dry-run ───────────────────────────────────────────────────
echo "==> [B] dry-run"
"$PYTHON" "$DRIVER" dryrun \
  --preflight-json "$PREFLIGHT_JSON" \
  --stamp "$STAMP" \
  --venue "$VENUE" \
  --since "$SINCE" \
  --org "$ORG" \
  --limit "$LIMIT" \
  --discrepancy-threshold "$DISCREPANCY_THRESHOLD" \
  --dryrun-report "$DRYRUN_REPORT"
echo "    dry-run report: $DRYRUN_REPORT"

if [ "$DRY_RUN_ONLY" -eq 1 ]; then
  echo "==> --dry-run-only set; stopping after stage B"
  exit 0
fi

# ── Stages C–F: apply / recompute / verify / publish ───────────────────
echo "==> [C-F] apply, recompute, verify, publish"
set +e
"$PYTHON" "$DRIVER" apply \
  --preflight-json "$PREFLIGHT_JSON" \
  --stamp "$STAMP" \
  --venue "$VENUE" \
  --since "$SINCE" \
  --org "$ORG" \
  --limit "$LIMIT" \
  --discrepancy-threshold "$DISCREPANCY_THRESHOLD" \
  --report "$REPORT"
APPLY_RC=$?
set -e
echo "    run report: $REPORT"

if [ "$APPLY_RC" -eq 5 ]; then
  echo "==> verify discrepancy over threshold — automation halted, founder review" >&2
  exit 5
elif [ "$APPLY_RC" -ne 0 ]; then
  echo "run_resolution_backfill: apply stage failed (rc=$APPLY_RC)" >&2
  exit "$APPLY_RC"
fi

echo "==> done"
exit 0
