"""Public-site viral-load simulator (CLI entry point).

Run a load profile against a deploy and write a results JSON. Exits
non-zero when the run violates the profile's budget — the GitHub
workflow uses that exit code to block the deploy.

Examples
--------
    # Light profile against the local dev server
    python tests/load/article_viral.py --profile light \
        --base-url http://127.0.0.1:3000 --article-slug some-slug

    # Viral profile against staging
    python tests/load/article_viral.py --profile viral \
        --base-url https://staging.theseus.example --article-slug some-slug

The article slug picks the page each session loads. Pass
``--conclusion-id`` if the article's lineage panel is rendered (so the
public lineage endpoint is exercised); omit it to skip that call.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import uuid
from pathlib import Path

# Allow ``python tests/load/article_viral.py`` from the repo root without
# an editable install. The library lives next door at ``tests/load/lib``.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from lib import runner  # noqa: E402


PROFILES_PATH = _HERE / "profiles.json"
RESULTS_DIR = _HERE / "results"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default="light",
        choices=["light", "viral", "spike"],
        help="Which profile from profiles.json to run.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LOAD_TEST_BASE_URL", "http://127.0.0.1:3000"),
        help="Deploy URL to hit. Defaults to $LOAD_TEST_BASE_URL or local dev.",
    )
    parser.add_argument(
        "--article-slug",
        default=os.environ.get("LOAD_TEST_ARTICLE_SLUG"),
        help="Slug of the article to load on /post/<slug>.",
    )
    parser.add_argument(
        "--conclusion-id",
        default=os.environ.get("LOAD_TEST_CONCLUSION_ID"),
        help="Optional conclusion id for /api/public/conclusion/<id>/lineage.",
    )
    parser.add_argument(
        "--concurrency-override",
        type=int,
        help="Override the profile's peak concurrency (e.g. for smoke runs).",
    )
    parser.add_argument(
        "--duration-override",
        type=int,
        help="Override the profile's duration in seconds.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Where to write the results JSON. Defaults to tests/load/results/.",
    )
    parser.add_argument(
        "--override-reason",
        default=os.environ.get("LOAD_TEST_OVERRIDE_REASON"),
        help=(
            "If set, a failing run will still exit 0 — the reason is recorded "
            "on the results JSON so the audit trail survives."
        ),
    )
    return parser.parse_args(argv)


def _isoformat(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])

    profile = runner.load_profile(args.profile, PROFILES_PATH)
    if args.concurrency_override is not None:
        profile = runner.LoadProfile(
            name=profile.name,
            concurrency=min(args.concurrency_override, profile.concurrency),
            peak_concurrency=args.concurrency_override,
            ramp_seconds=profile.ramp_seconds,
            duration_seconds=profile.duration_seconds,
            budget=profile.budget,
        )
    if args.duration_override is not None:
        profile = runner.LoadProfile(
            name=profile.name,
            concurrency=profile.concurrency,
            peak_concurrency=profile.peak_concurrency,
            ramp_seconds=min(profile.ramp_seconds, args.duration_override),
            duration_seconds=args.duration_override,
            budget=profile.budget,
        )

    run_id = uuid.uuid4().hex[:12]
    started_ts = _dt.datetime.now(_dt.timezone.utc).timestamp()

    print(
        f"[load] starting profile={profile.name} concurrency={profile.concurrency} "
        f"peak={profile.peak_concurrency} duration={profile.duration_seconds}s "
        f"budget=p50<{profile.budget.p50_ms:.0f}ms p95<{profile.budget.p95_ms:.0f}ms "
        f"err<{profile.budget.error_rate:.3f}",
        flush=True,
    )

    results = runner.run_profile(
        base_url=args.base_url,
        profile=profile,
        article_slug=args.article_slug,
        conclusion_id=args.conclusion_id,
        run_id=run_id,
    )
    finished_ts = _dt.datetime.now(_dt.timezone.utc).timestamp()
    stats = runner.aggregate(results)
    verdict = runner.evaluate(stats, profile.budget)

    report = runner.RunReport(
        profile=profile.name,
        started_at=_isoformat(started_ts),
        finished_at=_isoformat(finished_ts),
        base_url=args.base_url,
        article_slug=args.article_slug,
        stats=stats,
        budget=profile.budget,
        verdict=verdict,
        samples=len(results),
    )

    payload = runner.report_to_json(report)
    payload["runId"] = run_id
    if args.override_reason:
        payload["overrideReason"] = args.override_reason

    output_path = args.output or (
        RESULTS_DIR / f"run-{int(started_ts)}-{profile.name}-{run_id}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(
        f"[load] finished samples={stats.total} errors={stats.errors} "
        f"p50={stats.p50_ms:.0f}ms p95={stats.p95_ms:.0f}ms "
        f"err_rate={stats.error_rate:.3f} pool_exhaustion={stats.pool_exhaustion_events} "
        f"verdict={'PASS' if verdict.passed else 'FAIL'}",
        flush=True,
    )
    if not verdict.passed:
        for reason in verdict.reasons:
            print(f"[load]   ! {reason}", flush=True)

    print(f"[load] results written to {output_path}", flush=True)

    if verdict.passed:
        return 0
    if args.override_reason:
        print(
            f"[load] OVERRIDE: failing run accepted with reason: {args.override_reason}",
            flush=True,
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
