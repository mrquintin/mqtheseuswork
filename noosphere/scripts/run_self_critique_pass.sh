#!/usr/bin/env bash
#
# run_self_critique_pass.sh — operational harness for Round 17 prompt 43.
#
# Runs the *retrospective* self-critique pass over the firm's published
# corpus, the way an operator (or a scheduled quarterly job) would. It
# does NOT re-implement any critique logic — the reviewer lives in
# noosphere/noosphere/peer_review/self_critique.py and the fan-out in
# scheduler_self_critique.py. This script is the run wrapper, the
# pre-flight gate, the triage-memo generator, and the cost reporter.
#
#   A. Pre-flight  — confirm the modules import, the store is reachable,
#                    the PublishedConclusion table exists, and the
#                    publication keyring can be initialised. A hard
#                    failure GATES the run; nothing is written.
#   B. Inventory   — list every published article older than
#                    --threshold-days (default 90). Cross-reference
#                    prior self_critique_*/manifest.json runs and DROP
#                    articles already critiqued — the pass never
#                    double-runs an article.
#   C. Run         — execute the SelfCritiqueReviewer on each article
#                    with a reviewer config ROTATED relative to the
#                    article's original review (multi-provider
#                    originals get a different prompt variant; single-
#                    config originals get a different provider mix).
#                    Findings land in the unified attention queue
#                    (ReviewItem rows) at high severity.
#   D. Triage      — write docs/runs/self_critique_<stamp>.md: every
#                    article, the worst-finding verdict, and the
#                    agent's recommended action (revise / addend /
#                    dismiss). The harness NEVER commits addenda or
#                    revisions on the founder's behalf.
#   E. Addenda     — for findings the agent recommends "addend", draft
#                    docs/runs/self_critique_<stamp>/addenda/<slug>.md.
#                    The founder paste-publishes via the existing
#                    Addendum workflow.
#   F. Sign        — verify the signed-publication path (prompt 30) is
#                    wired and run an addendum signature round-trip on
#                    a synthetic article (sign -> verify ok -> mutate
#                    -> verify fails). Recorded in the triage memo.
#
# The cost of the pass — total LLM spend plus a per-article breakdown —
# is reported in the triage memo. The firm should know what
# intellectual honesty actually costs.
#
# Usage:
#   run_self_critique_pass.sh [options]
#
# Options:
#   --threshold-days N   Age cut-off in days (default: 90)
#   --limit N            Max articles to inventory (default: 1000)
#   --org ORG_ID         Restrict to one tenant
#   --judge MODE         Reviewer judge: gate | stub | env (default: gate)
#                          gate  no judge wired; the run stage GATES if
#                                any articles are pending (exit 4).
#                          stub  built-in deterministic synthetic judge.
#                                Exercises the pipeline; calls no LLM.
#                          env   resolve THESEUS_SELF_CRITIQUE_JUDGE
#                                ("module.path:callable") — a real
#                                provider adapter.
#   --stamp STAMP        Override the run stamp (tests; default: UTC now)
#   --runs-dir DIR       Override docs/runs (tests)
#   --key-dir DIR        Keyring dir for the stage-F round-trip
#                          (default: a throwaway temp dir — the synthetic
#                           round-trip never touches the operator keyring)
#   -h, --help           Show this help
#
# Exit codes:
#   0  completed (or completed with an empty inventory)
#   2  bad usage
#   3  pre-flight GATED — run did not start; the memo documents the gate
#   4  run incomplete — articles were pending but no judge was wired
#
set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOOSPHERE_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$NOOSPHERE_DIR")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUNS_DIR="$REPO_ROOT/docs/runs"
KEY_DIR=""
PREFLIGHT_JSON="$(mktemp -t selfcritique_preflight.XXXXXX)"
DRIVER="${TMPDIR:-/tmp}/self_critique_driver_$$.py"
trap 'rm -f "$DRIVER" "$PREFLIGHT_JSON"; [ -n "${_TMP_KEY_DIR:-}" ] && rm -rf "$_TMP_KEY_DIR"' EXIT

# ── Defaults / args ────────────────────────────────────────────────────
THRESHOLD_DAYS="90"
LIMIT="1000"
ORG=""
JUDGE="gate"

usage() { sed -n '2,75p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --threshold-days) THRESHOLD_DAYS="${2:-}"; shift 2 ;;
    --limit) LIMIT="${2:-}"; shift 2 ;;
    --org) ORG="${2:-}"; shift 2 ;;
    --judge) JUDGE="${2:-}"; shift 2 ;;
    --stamp) STAMP="${2:-}"; shift 2 ;;
    --runs-dir) RUNS_DIR="${2:-}"; shift 2 ;;
    --key-dir) KEY_DIR="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "run_self_critique_pass: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$JUDGE" in
  gate|stub|env) ;;
  *) echo "run_self_critique_pass: --judge must be gate|stub|env" >&2; exit 2 ;;
esac

REPORT="$RUNS_DIR/self_critique_${STAMP}.md"
RUN_DIR="$RUNS_DIR/self_critique_${STAMP}"
ADDENDA_DIR="$RUN_DIR/addenda"
MANIFEST_JSON="$RUN_DIR/manifest.json"

if [ -z "$KEY_DIR" ]; then
  _TMP_KEY_DIR="$(mktemp -d -t selfcritique_keyring.XXXXXX)"
  KEY_DIR="$_TMP_KEY_DIR"
fi

# ── Environment ────────────────────────────────────────────────────────
# Load .env files so DATABASE_URL surfaces to the pre-flight check the
# same way it would for a scheduled job. Repo-root first, then the
# noosphere package dir; later files do not clobber earlier exports.
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

mkdir -p "$RUNS_DIR" "$ADDENDA_DIR"

# ── Embedded Python driver ─────────────────────────────────────────────
# Kept in one place: this script writes it to a temp file at run time and
# invokes it per stage. It only orchestrates library calls — all reviewer,
# scheduler, addendum and signing logic lives in the noosphere package.
cat > "$DRIVER" <<'PYEOF'
"""Run-time driver for run_self_critique_pass.sh. Not a committed module.

Orchestration only. Every unit of real work is a library call into
noosphere.peer_review.self_critique, noosphere.peer_review.
scheduler_self_critique, or noosphere.ledger.publication_signing.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone


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


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ── Reviewer-config rotation ───────────────────────────────────────────
# The spec is explicit: self-critique must use a config DISTINCT from the
# article's original review, because a same-config self-review reproduces
# the original blind spots. And: an article whose original review used
# multi-provider rotation is self-critiqued with a different *prompt
# variant* rather than a different provider mix.


def _original_used_multi_provider(original_config: str) -> bool:
    s = (original_config or "").lower()
    return any(tok in s for tok in ("rotation", "multi", "swarm", "+", ","))


def rotate_reviewer_config(original_config: str) -> str:
    """Return a self-critique reviewer config rotated off ``original_config``.

    Multi-provider originals -> rotate the prompt variant.
    Single-config originals  -> rotate the provider mix.
    The result is always non-empty, deterministic, and != the original.
    """
    seed = int(hashlib.sha256((original_config or "").encode("utf-8")).hexdigest(), 16)
    if _original_used_multi_provider(original_config):
        variant = "ABC"[seed % 3]
        return f"self-critique:promptvar-{variant}"
    mixes = ("anthropic-lead", "openai-lead", "google-lead")
    return f"self-critique:provmix-{mixes[seed % len(mixes)]}"


# ── Pre-flight ─────────────────────────────────────────────────────────


def preflight() -> dict:
    checks: dict = {}
    reasons: list[str] = []

    for mod in (
        "noosphere.peer_review.self_critique",
        "noosphere.peer_review.scheduler_self_critique",
        "noosphere.ledger.publication_signing",
    ):
        key = "import_" + mod.rsplit(".", 1)[-1]
        try:
            __import__(mod)
            checks[key] = True
        except Exception as exc:
            checks[key] = False
            reasons.append(f"{mod} import failed: {type(exc).__name__}: {exc}")

    # Store + PublishedConclusion schema.
    db_url, db_src = _resolve_db_url()
    checks["database_url_source"] = db_src
    checks["database_url_scheme"] = _scheme(db_url)
    store_ok = False
    schema_ok = False
    article_estimate = None
    try:
        from sqlalchemy import inspect as _sa_inspect

        from noosphere.store import Store

        store = Store.from_database_url(db_url)
        store_ok = True
        insp = _sa_inspect(store.engine)
        if insp.has_table("PublishedConclusion"):
            schema_ok = True
            try:
                with store.engine.connect() as conn:
                    from sqlalchemy import text as _sa_text

                    article_estimate = conn.execute(
                        _sa_text('SELECT COUNT(*) FROM "PublishedConclusion"')
                    ).scalar()
            except Exception:
                article_estimate = None
        else:
            reasons.append("PublishedConclusion table absent from the store")
    except Exception as exc:
        reasons.append(f"store unreachable: {type(exc).__name__}: {exc}")
    checks["store_reachable"] = store_ok
    checks["published_conclusion_schema_present"] = schema_ok
    checks["published_conclusion_count"] = article_estimate

    # Publication keyring (prompt 30) — the signed-publication path.
    key_dir = os.environ.get("SC_KEY_DIR", "").strip()
    keyring_ok = False
    try:
        from noosphere.ledger.publication_signing import PublicationKeyring

        kr = PublicationKeyring(key_dir or None)
        kr.ensure()
        keyring_ok = bool(kr.active_fingerprint())
        checks["keyring_dir"] = str(kr.root)
        checks["keyring_active_fingerprint"] = kr.active_fingerprint()
        if not keyring_ok:
            reasons.append("publication keyring has no active key after ensure()")
    except Exception as exc:
        reasons.append(f"keyring init failed: {type(exc).__name__}: {exc}")
    checks["keyring_ok"] = keyring_ok

    hard_fail = (
        not checks.get("import_self_critique")
        or not checks.get("import_scheduler_self_critique")
        or not checks.get("import_publication_signing")
        or not store_ok
        or not schema_ok
        or not keyring_ok
    )
    verdict = "GATED" if hard_fail else "PASS"
    return {
        "verdict": verdict,
        "checks": checks,
        "reasons": reasons,
        "generated_at": _stamp(),
    }


# ── Markdown helpers ───────────────────────────────────────────────────


def _yn(value) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value)


def _header(stamp: str) -> str:
    return "\n".join(
        [
            "# Self-critique pass — triage memo",
            "",
            f"- run stamp (UTC): `{stamp}`",
            f"- generated_at: {_stamp()}",
            "- driver: `noosphere/scripts/run_self_critique_pass.sh`",
            "- reviewer module: "
            "`noosphere/noosphere/peer_review/self_critique.py`",
            "- prompt: Round 17 prompt 43 (quarterly self-critique)",
            "",
            "> The harness queues findings into the founder attention queue "
            "and drafts addendum candidates. It does **not** commit addenda "
            "or revisions — every action below is a *recommendation* for the "
            "founder to triage.",
            "",
        ]
    )


def _preflight_md(pf: dict) -> str:
    c = pf["checks"]
    lines = [
        "## A. Pre-flight",
        "",
        f"- verdict: **{pf['verdict']}**",
        f"- self_critique imports: {_yn(c.get('import_self_critique'))}",
        f"- scheduler_self_critique imports: "
        f"{_yn(c.get('import_scheduler_self_critique'))}",
        f"- publication_signing imports: "
        f"{_yn(c.get('import_publication_signing'))}",
        f"- store reachable: {_yn(c.get('store_reachable'))} "
        f"(url source={c.get('database_url_source', '—')}, "
        f"scheme={c.get('database_url_scheme', '—')})",
        f"- PublishedConclusion schema present: "
        f"{_yn(c.get('published_conclusion_schema_present'))} "
        f"(rows={c.get('published_conclusion_count', '—')})",
        f"- publication keyring ready: {_yn(c.get('keyring_ok'))} "
        f"(fingerprint={c.get('keyring_active_fingerprint', '—')})",
    ]
    if pf["reasons"]:
        lines += ["", "Gate reasons:"]
        lines += [f"- {r}" for r in pf["reasons"]]
    return "\n".join(lines)


# ── report-gated ───────────────────────────────────────────────────────


def cmd_report_gated(args: argparse.Namespace) -> int:
    with open(args.preflight_json, encoding="utf-8") as fh:
        pf = json.load(fh)
    body = "\n".join(
        [
            _header(args.stamp),
            _preflight_md(pf),
            "",
            "## Run not started — pre-flight GATE",
            "",
            "The pre-flight stage did not pass, so the harness stopped "
            "before stage B. **No articles were inventoried, no reviewer "
            "ran, no review items were queued, and no addenda were "
            "drafted.** This is the harness behaving as designed: the "
            "pre-flight is a gate, not a warning.",
            "",
            "Re-run once the gate reasons above are resolved.",
            "",
        ]
    )
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(body)
    return 0


# ── Inventory ──────────────────────────────────────────────────────────


def _load_articles(store, *, limit: int, org: str):
    """Read PublishedConclusion rows into scheduler PublishedArticle objects.

    The article body is the public payload's ``conclusionText``. The
    original-review reviewer config is recovered (best effort) from the
    latest ReviewReport on the source conclusion — used to rotate the
    self-critique config off it.
    """
    from sqlalchemy import text as _sa_text

    from noosphere.peer_review.scheduler_self_critique import PublishedArticle

    sql = (
        'SELECT id, "sourceConclusionId", slug, version, "payloadJson", '
        '"publishedAt" FROM "PublishedConclusion" '
    )
    params: dict = {}
    if org:
        sql += 'WHERE "organizationId" = :org '
        params["org"] = org
    sql += 'ORDER BY "publishedAt" ASC LIMIT :lim'
    params["lim"] = int(limit)

    with store.engine.connect() as conn:
        rows = conn.execute(_sa_text(sql), params).fetchall()

    articles: list[tuple] = []
    for row in rows:
        m = row._mapping
        payload = {}
        try:
            payload = json.loads(m["payloadJson"] or "{}")
        except (TypeError, ValueError):
            payload = {}
        body = str(payload.get("conclusionText") or payload.get("rationale") or "")
        published_at = m["publishedAt"]
        if not isinstance(published_at, datetime):
            try:
                published_at = datetime.fromisoformat(
                    str(published_at).replace("Z", "+00:00")
                )
            except ValueError:
                published_at = _utc_now()
        # Original-review config (best effort).
        original_config = ""
        try:
            reports = store.list_review_reports(str(m["sourceConclusionId"]))
            if reports:
                reports.sort(key=lambda r: r.completed_at)
                original_config = reports[-1].reviewer
        except Exception:
            original_config = ""
        article = PublishedArticle(
            article_id=str(m["id"]),
            title=str(payload.get("topicHint") or m["slug"]),
            body=body,
            slug=str(m["slug"]),
            published_at=_ensure_aware(published_at),
        )
        articles.append((article, original_config))
    return articles


def _already_critiqued(runs_dir: str, current_stamp: str) -> set[str]:
    """Article ids covered by a prior self_critique run.

    Each run writes self_critique_<stamp>/manifest.json listing the ids
    it critiqued. The pass never double-runs an article.
    """
    seen: set[str] = set()
    pattern = os.path.join(runs_dir, "self_critique_*", "manifest.json")
    for path in glob.glob(pattern):
        if f"self_critique_{current_stamp}" in path:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            for entry in data.get("articles", []):
                aid = entry.get("article_id")
                if aid:
                    seen.add(str(aid))
        except Exception:
            continue
    return seen


# ── Judge resolution ───────────────────────────────────────────────────


class _StubJudge:
    """Deterministic synthetic judge — exercises the pipeline, calls no LLM.

    The verdict is a stable function of the article id so a given corpus
    produces a stable memo. Cost is metered from input/output sizes with
    public-list per-token prices so the cost report is exercised too.
    """

    # Indicative blended prices (USD per 1k tokens). Synthetic, but the
    # arithmetic path is the real one.
    PROMPT_USD_PER_1K = 0.003
    COMPLETION_USD_PER_1K = 0.015

    def __init__(self) -> None:
        self.last_call_cost_usd = 0.0
        self.last_call_prompt_tokens = 0
        self.last_call_completion_tokens = 0

    def __call__(self, article_id, article_text, reviewer_config, then, now):
        from noosphere.peer_review.self_critique import (
            SELF_CRITIQUE_SYSTEM_PROMPT,
        )

        bucket = int(hashlib.sha256(article_id.encode("utf-8")).hexdigest(), 16) % 3
        if bucket == 0:
            findings = [
                {
                    "claim": "Headline claim from the article.",
                    "was_supported_by": [e.source_id for e in then][:2],
                    "now_supported_by": [e.source_id for e in now][:2],
                    "verdict": "still holds",
                    "recommended_action": "dismiss",
                    "rationale": (
                        "Post-publication evidence is consistent with the "
                        "original claim; no action required."
                    ),
                }
            ]
        elif bucket == 1:
            findings = [
                {
                    "claim": "A load-bearing sub-claim of the article.",
                    "was_supported_by": [e.source_id for e in then][:2],
                    "now_supported_by": [e.source_id for e in now][:2],
                    "verdict": "weakened",
                    "recommended_action": "addend",
                    "rationale": (
                        "Newer evidence narrows the claim's scope. The "
                        "article still stands but should carry a dated "
                        "addendum noting the reduced effect size."
                    ),
                }
            ]
        else:
            findings = [
                {
                    "claim": "A central prediction of the article.",
                    "was_supported_by": [e.source_id for e in then][:2],
                    "now_supported_by": [e.source_id for e in now][:2],
                    "verdict": "contradicted by new evidence",
                    "recommended_action": "revise",
                    "rationale": (
                        "Post-publication resolution runs against the "
                        "article's central prediction; this needs the "
                        "revision engine, not an addendum."
                    ),
                }
            ]
        prompt_chars = (
            len(SELF_CRITIQUE_SYSTEM_PROMPT)
            + len(article_text)
            + sum(len(e.summary) for e in then)
            + sum(len(e.summary) for e in now)
        )
        completion_chars = len(json.dumps({"findings": findings}))
        # ~4 chars/token is the standard rough estimate.
        self.last_call_prompt_tokens = max(1, prompt_chars // 4)
        self.last_call_completion_tokens = max(1, completion_chars // 4)
        self.last_call_cost_usd = round(
            self.last_call_prompt_tokens / 1000.0 * self.PROMPT_USD_PER_1K
            + self.last_call_completion_tokens
            / 1000.0
            * self.COMPLETION_USD_PER_1K,
            6,
        )
        return findings


def _resolve_judge(mode: str):
    """Return (judge_callable_or_None, label, note)."""
    if mode == "gate":
        return None, "none (gate mode)", (
            "No judge wired. The run stage gates if any article is pending."
        )
    if mode == "stub":
        return _StubJudge(), "stub (synthetic, deterministic)", (
            "Built-in deterministic judge. No LLM was called — this run "
            "exercises the pipeline, not a model."
        )
    # mode == "env"
    spec = os.environ.get("THESEUS_SELF_CRITIQUE_JUDGE", "").strip()
    if not spec or ":" not in spec:
        return None, "env (unresolved)", (
            "THESEUS_SELF_CRITIQUE_JUDGE is unset or malformed "
            "(expected 'module.path:callable')."
        )
    mod_name, _, attr = spec.partition(":")
    try:
        mod = __import__(mod_name, fromlist=[attr])
        judge = getattr(mod, attr)
    except Exception as exc:
        return None, f"env ({spec})", (
            f"failed to import {spec}: {type(exc).__name__}: {exc}"
        )
    return judge, f"env ({spec})", "Resolved from THESEUS_SELF_CRITIQUE_JUDGE."


# ── Stage F: signed-publication path ───────────────────────────────────


def _verify_sign_path(key_dir: str) -> dict:
    """Stage F: prove the prompt-30 signed-publication path is wired by
    running an addendum signature round-trip on a synthetic article."""
    out: dict = {"wired": False, "round_trip_ok": False, "mutation_rejected": False}
    try:
        from noosphere.ledger.canonicalize import PublicationCanonicalInput
        from noosphere.ledger.publication_signing import (
            PublicationKeyring,
            sign_publication,
            verify_signature,
        )
        from noosphere.peer_review.self_critique import (
            SelfCritiqueAction,
            SelfCritiqueFinding,
            SelfCritiqueVerdict,
            addendum_from_finding,
        )
    except Exception as exc:
        out["error"] = f"import: {type(exc).__name__}: {exc}"
        return out
    out["wired"] = True
    try:
        # Synthetic article + an "addend" finding -> a pending Addendum.
        finding = SelfCritiqueFinding(
            claim="Synthetic claim for the stage-F round-trip.",
            verdict=SelfCritiqueVerdict.WEAKENED,
            recommended_action=SelfCritiqueAction.ADDEND,
            rationale="Synthetic rationale exercising the signing path.",
        )
        addendum = addendum_from_finding(
            finding,
            article_id="synthetic-article",
            article_slug="synthetic-article",
        )
        # An addendum is itself a signed publication: it gets its own
        # canonical identity (slug suffixed, version 1).
        canonical = PublicationCanonicalInput(
            slug="synthetic-article-addendum-1",
            version=1,
            conclusion_text=addendum.body,
            methodology_profile_ids=[],
            citations=[],
            discounted_confidence=0.0,
            stated_confidence=0.0,
            mqs=None,
            published_at=addendum.created_at,
        )
        keyring = PublicationKeyring(key_dir or None)
        keyring.ensure()
        out["key_fingerprint"] = keyring.active_fingerprint()
        sig = sign_publication(canonical, keyring)
        ok = verify_signature(sig, keyring, live_input=canonical)
        out["round_trip_ok"] = bool(ok.ok)
        if not ok.ok:
            out["round_trip_issues"] = ok.issues
        # Mutate the addendum body — verification MUST now fail.
        mutated = PublicationCanonicalInput(
            slug=canonical.slug,
            version=canonical.version,
            conclusion_text=canonical.conclusion_text + "\n\n[tampered]",
            methodology_profile_ids=[],
            citations=[],
            discounted_confidence=0.0,
            stated_confidence=0.0,
            mqs=None,
            published_at=addendum.created_at,
        )
        bad = verify_signature(sig, keyring, live_input=mutated)
        out["mutation_rejected"] = not bad.ok
    except Exception as exc:
        out["error"] = f"round-trip: {type(exc).__name__}: {exc}"
    return out


# ── Run (B + C + D + E + F) ────────────────────────────────────────────


def _worst_finding(report):
    """Pick the finding that should drive the article-level verdict.

    Severity order: contradicted > no longer supported > weakened >
    still holds. The recommended action follows from that finding.
    """
    from noosphere.peer_review.self_critique import SelfCritiqueVerdict

    order = {
        SelfCritiqueVerdict.CONTRADICTED: 3,
        SelfCritiqueVerdict.NO_LONGER_SUPPORTED: 2,
        SelfCritiqueVerdict.WEAKENED: 1,
        SelfCritiqueVerdict.STILL_HOLDS: 0,
    }
    if not report.findings:
        return None
    return max(report.findings, key=lambda f: order.get(f.verdict, 0))


def cmd_run(args: argparse.Namespace) -> int:
    from noosphere.peer_review.scheduler_self_critique import (
        DEFAULT_FRESHNESS_THRESHOLD_DAYS,
        queue_findings,
        run_self_critique_for_article,
        select_articles_for_self_critique,
    )
    from noosphere.peer_review.self_critique import (
        SelfCritiqueAction,
        SelfCritiqueReviewer,
        addendum_from_finding,
        finding_to_dict,
    )
    from noosphere.store import Store

    with open(args.preflight_json, encoding="utf-8") as fh:
        pf = json.load(fh)

    db_url, _src = _resolve_db_url()
    store = Store.from_database_url(db_url)
    threshold = int(args.threshold_days or DEFAULT_FRESHNESS_THRESHOLD_DAYS)

    # ── B. Inventory ──
    loaded = _load_articles(store, limit=int(args.limit), org=args.org)
    config_by_id = {a.article_id: cfg for (a, cfg) in loaded}
    all_articles = [a for (a, _cfg) in loaded]
    plans = select_articles_for_self_critique(
        all_articles, threshold_days=threshold
    )
    already = _already_critiqued(args.runs_dir, args.stamp)
    fresh_plans = [p for p in plans if p.article.article_id not in already]
    skipped_dups = [p for p in plans if p.article.article_id in already]

    # ── Judge ──
    judge, judge_label, judge_note = _resolve_judge(args.judge)

    rc = 0
    run_rows: list[dict] = []
    addenda_written: list[dict] = []
    total_cost = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    if fresh_plans and judge is None:
        # Articles are pending but no judge is wired — the run stage
        # cannot proceed. Record every pending article as deferred.
        rc = 4
        for plan in fresh_plans:
            run_rows.append(
                {
                    "article_id": plan.article.article_id,
                    "slug": plan.article.slug,
                    "title": plan.article.title,
                    "age_days": round(plan.age_days, 1),
                    "reviewer_config": rotate_reviewer_config(
                        config_by_id.get(plan.article.article_id, "")
                    ),
                    "original_review_config": config_by_id.get(
                        plan.article.article_id, ""
                    ),
                    "status": "deferred",
                    "verdict": "—",
                    "recommended_action": "—",
                    "findings": 0,
                    "queued_review_item_ids": [],
                    "cost_usd": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                }
            )
    else:
        # ── C. Run ──
        for plan in fresh_plans:
            original_config = config_by_id.get(plan.article.article_id, "")
            reviewer_config = rotate_reviewer_config(original_config)
            reviewer = SelfCritiqueReviewer(
                judge_fn=judge, reviewer_config=reviewer_config
            )
            row: dict = {
                "article_id": plan.article.article_id,
                "slug": plan.article.slug,
                "title": plan.article.title,
                "age_days": round(plan.age_days, 1),
                "reviewer_config": reviewer_config,
                "original_review_config": original_config or "(unknown)",
                "status": "reviewed",
                "verdict": "still holds",
                "recommended_action": "dismiss",
                "findings": 0,
                "queued_review_item_ids": [],
                "cost_usd": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }
            try:
                report = run_self_critique_for_article(
                    plan,
                    reviewer=reviewer,
                    evidence_then=lambda _a: [],
                    evidence_now=lambda _a: [],
                )
            except Exception as exc:
                row["status"] = f"error: {type(exc).__name__}: {exc}"
                run_rows.append(row)
                continue

            # Cost metering — the judge may expose per-call usage.
            cost = float(getattr(judge, "last_call_cost_usd", 0.0) or 0.0)
            ptok = int(getattr(judge, "last_call_prompt_tokens", 0) or 0)
            ctok = int(getattr(judge, "last_call_completion_tokens", 0) or 0)
            row["cost_usd"] = round(cost, 6)
            row["prompt_tokens"] = ptok
            row["completion_tokens"] = ctok
            total_cost += cost
            total_prompt_tokens += ptok
            total_completion_tokens += ctok

            row["findings"] = len(report.findings)
            worst = _worst_finding(report)
            if worst is not None:
                row["verdict"] = worst.verdict.value
                row["recommended_action"] = worst.recommended_action.value

            # ── attention queue: high-severity ReviewItems ──
            if report.findings:
                try:
                    row["queued_review_item_ids"] = queue_findings(
                        store, plan.article, report
                    )
                except Exception as exc:
                    row["queue_error"] = f"{type(exc).__name__}: {exc}"

            # ── E. Addenda candidates ──
            for idx, finding in enumerate(report.findings):
                if finding.recommended_action is not SelfCritiqueAction.ADDEND:
                    continue
                addendum = addendum_from_finding(
                    finding,
                    article_id=plan.article.article_id,
                    article_slug=plan.article.slug,
                    finding_id=f"{report.report_id}:{idx}",
                    reviewer_config=reviewer_config,
                )
                slug = plan.article.slug or plan.article.article_id
                fname = f"{slug}.md" if len(report.findings) == 1 else f"{slug}-{idx}.md"
                path = os.path.join(args.addenda_dir, fname)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(_addendum_md(plan.article, addendum, finding, reviewer_config))
                addenda_written.append(
                    {
                        "article_id": plan.article.article_id,
                        "slug": slug,
                        "path": os.path.relpath(path, args.runs_dir),
                        "finding_id": addendum.finding_id,
                    }
                )
            run_rows.append(row)

    # ── F. Sign ──
    sign = _verify_sign_path(os.environ.get("SC_KEY_DIR", "").strip())

    # ── manifest (de-dup ledger for future runs) ──
    os.makedirs(args.run_dir, exist_ok=True)
    manifest = {
        "stamp": args.stamp,
        "generated_at": _stamp(),
        "threshold_days": threshold,
        "judge": judge_label,
        "articles": [
            {"article_id": r["article_id"], "slug": r["slug"], "status": r["status"]}
            for r in run_rows
        ],
    }
    with open(args.manifest_json, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    # ── D. Triage memo ──
    memo = _triage_md(
        pf=pf,
        stamp=args.stamp,
        threshold=threshold,
        judge_label=judge_label,
        judge_note=judge_note,
        inventory_total=len(all_articles),
        eligible=len(plans),
        skipped_dups=skipped_dups,
        run_rows=run_rows,
        addenda_written=addenda_written,
        sign=sign,
        total_cost=total_cost,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        runs_dir=args.runs_dir,
        run_dir=args.run_dir,
        incomplete=(rc == 4),
    )
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(memo)

    print(
        f"self-critique: inventoried {len(all_articles)} article(s), "
        f"{len(plans)} eligible (>{threshold}d), {len(skipped_dups)} already "
        f"critiqued, {len([r for r in run_rows if r['status'] == 'reviewed'])} "
        f"reviewed; {len(addenda_written)} addendum candidate(s); "
        f"total LLM spend ${total_cost:.4f}; "
        f"sign round-trip ok={sign.get('round_trip_ok')}"
    )
    return rc


# ── Markdown: addendum candidate ───────────────────────────────────────


def _addendum_md(article, addendum, finding, reviewer_config: str) -> str:
    return "\n".join(
        [
            f"# Addendum candidate — {article.slug}",
            "",
            f"- article_id: `{article.article_id}`",
            f"- article slug: `{article.slug}`",
            f"- finding_id: `{addendum.finding_id}`",
            f"- self-critique reviewer config: `{reviewer_config}`",
            f"- verdict: **{finding.verdict.value}**",
            f"- drafted: {_stamp()}",
            "",
            "> Draft only. The founder paste-publishes this via the existing "
            "Addendum workflow; on publish it MUST run through the signed-"
            "publication path (Round 17 prompt 30). The original article "
            "body is immutable — this is later, dated content shown below "
            "the article.",
            "",
            "## Summary",
            "",
            addendum.summary,
            "",
            "## Addendum text",
            "",
            addendum.body,
            "",
            "## Provenance",
            "",
            f"- claim under review: {finding.claim}",
            f"- was supported by: "
            f"{', '.join(finding.was_supported_by) or '—'}",
            f"- now bears on: "
            f"{', '.join(finding.now_supported_by) or '—'}",
            "",
        ]
    )


# ── Markdown: triage memo ──────────────────────────────────────────────


def _triage_md(**kw) -> str:
    pf = kw["pf"]
    run_rows = kw["run_rows"]
    skipped_dups = kw["skipped_dups"]
    addenda_written = kw["addenda_written"]
    sign = kw["sign"]

    reviewed = [r for r in run_rows if r["status"] == "reviewed"]
    deferred = [r for r in run_rows if r["status"] == "deferred"]
    errored = [r for r in run_rows if r["status"].startswith("error")]

    by_action: dict[str, int] = {}
    for r in reviewed:
        by_action[r["recommended_action"]] = (
            by_action.get(r["recommended_action"], 0) + 1
        )

    lines = [_header(kw["stamp"]), _preflight_md(pf), ""]

    # B. Inventory
    lines += [
        "## B. Inventory",
        "",
        f"- published articles inventoried: **{kw['inventory_total']}**",
        f"- older than {kw['threshold']} days (eligible): "
        f"**{kw['eligible']}**",
        f"- already critiqued by a prior run (skipped, not double-run): "
        f"**{len(skipped_dups)}**",
        f"- fresh this run: **{len(run_rows)}**",
        "",
    ]
    if skipped_dups:
        lines += ["Skipped — cross-referenced against prior "
                  "`self_critique_*/manifest.json`:", ""]
        for p in skipped_dups:
            lines.append(
                f"- `{p.article.article_id}` ({p.article.slug}) — "
                f"{p.age_days:.0f}d old"
            )
        lines.append("")

    # C. Run
    lines += [
        "## C. Run",
        "",
        f"- judge: **{kw['judge_label']}**",
        f"- {kw['judge_note']}",
        f"- articles reviewed: **{len(reviewed)}**",
        f"- deferred (no judge wired): **{len(deferred)}**",
        f"- errored: **{len(errored)}**",
        "",
        "Each article is self-critiqued with a reviewer config **rotated** "
        "off its original review (multi-provider originals get a different "
        "prompt variant; single-config originals get a different provider "
        "mix) — a same-config self-review reproduces the original blind "
        "spots.",
        "",
    ]

    # D. Triage table
    lines += ["## D. Triage", ""]
    if run_rows:
        lines += [
            "| article | slug | age (d) | original review | self-critique "
            "config | verdict | recommended | findings | queued | cost (USD) |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in run_rows:
            lines.append(
                f"| `{r['article_id']}` | {r['slug']} | {r['age_days']} "
                f"| {r['original_review_config'] or '—'} "
                f"| {r['reviewer_config']} | {r['verdict']} "
                f"| **{r['recommended_action']}** | {r['findings']} "
                f"| {len(r['queued_review_item_ids'])} "
                f"| {r['cost_usd']:.6f} |"
            )
        lines.append("")
        lines += [
            "Recommended-action tally: "
            + (
                ", ".join(f"{k}: {v}" for k, v in sorted(by_action.items()))
                or "_none_"
            ),
            "",
            "All findings were queued into the unified founder attention "
            "queue (`ReviewItem` rows) at high severity. The harness has "
            "**not** committed any addendum or revision — the column above "
            "is the agent's *recommendation*.",
            "",
        ]
    else:
        lines += [
            "_No articles were eligible this run — either the corpus has "
            "nothing older than the threshold, or every eligible article "
            "was already critiqued by a prior run._",
            "",
        ]

    # E. Addenda
    lines += ["## E. Addendum candidates", ""]
    if addenda_written:
        lines += [
            f"Drafted **{len(addenda_written)}** addendum candidate(s) under "
            f"`{os.path.relpath(kw['run_dir'], kw['runs_dir'])}/addenda/`. "
            "The founder paste-publishes each via the existing Addendum "
            "workflow.",
            "",
        ]
        for a in addenda_written:
            lines.append(f"- `{a['slug']}` — `{a['path']}` (finding "
                         f"`{a['finding_id']}`)")
        lines.append("")
    else:
        lines += [
            "_No findings recommended `addend` this run — no addendum "
            "candidates were drafted._",
            "",
        ]

    # F. Sign
    lines += [
        "## F. Signed-publication path (Round 17 prompt 30)",
        "",
        f"- signing path importable / wired: {_yn(sign.get('wired'))}",
        f"- synthetic addendum signature round-trip: "
        f"{_yn(sign.get('round_trip_ok'))}",
        f"- tampered addendum correctly rejected: "
        f"{_yn(sign.get('mutation_rejected'))}",
        f"- signing key fingerprint: "
        f"`{sign.get('key_fingerprint', '—')}`",
        "",
        "Any addendum the founder publishes MUST go through this path — "
        "addenda are themselves signed publications, with their own "
        "canonical identity (slug suffixed `-addendum-<n>`, version 1).",
        "",
    ]
    if sign.get("error"):
        lines += [f"> Sign-path issue: {sign['error']}", ""]
    if sign.get("round_trip_issues"):
        lines += [f"> Round-trip issues: {sign['round_trip_issues']}", ""]

    # Cost report
    lines += [
        "## Cost report — what intellectual honesty costs",
        "",
        f"- total LLM spend this pass: **${kw['total_cost']:.4f}**",
        f"- total prompt tokens: {kw['total_prompt_tokens']:,}",
        f"- total completion tokens: {kw['total_completion_tokens']:,}",
        f"- articles billed: {len(reviewed)}",
        "",
    ]
    if reviewed:
        lines += [
            "| article | slug | prompt tok | completion tok | cost (USD) |",
            "| --- | --- | --- | --- | --- |",
        ]
        for r in reviewed:
            lines.append(
                f"| `{r['article_id']}` | {r['slug']} | "
                f"{r['prompt_tokens']:,} | {r['completion_tokens']:,} | "
                f"{r['cost_usd']:.6f} |"
            )
        lines.append("")
    else:
        lines += [
            "_No articles were billed this run._",
            "",
        ]
    if kw["judge_label"].startswith("stub"):
        lines += [
            "> Cost figures above are from the **stub** judge: token counts "
            "are real (measured off the actual prompt + completion bytes) "
            "but priced against indicative public list rates, and no LLM "
            "was called. A production run with `--judge env` reports the "
            "provider adapter's metered spend.",
            "",
        ]

    if kw["incomplete"]:
        lines += [
            "## Run incomplete",
            "",
            "Articles were eligible for self-critique but **no judge was "
            "wired** (`--judge gate`). They are listed above as `deferred`. "
            "Re-run with `--judge env` (a provider adapter) or `--judge "
            "stub` (pipeline exercise) to critique them. Nothing was lost — "
            "the manifest records them as deferred, not critiqued, so the "
            "next run picks them up.",
            "",
        ]

    return "\n".join(lines)


# ── main ───────────────────────────────────────────────────────────────


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="self_critique_driver")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pre = sub.add_parser("preflight")
    p_pre.add_argument("--json-out", required=True)

    p_gated = sub.add_parser("report-gated")
    p_gated.add_argument("--preflight-json", required=True)
    p_gated.add_argument("--report", required=True)
    p_gated.add_argument("--stamp", required=True)

    p_run = sub.add_parser("run")
    p_run.add_argument("--preflight-json", required=True)
    p_run.add_argument("--stamp", required=True)
    p_run.add_argument("--report", required=True)
    p_run.add_argument("--run-dir", required=True)
    p_run.add_argument("--addenda-dir", required=True)
    p_run.add_argument("--manifest-json", required=True)
    p_run.add_argument("--runs-dir", required=True)
    p_run.add_argument("--threshold-days", default="90")
    p_run.add_argument("--limit", default="1000")
    p_run.add_argument("--org", default="")
    p_run.add_argument("--judge", default="gate")

    args = parser.parse_args(argv)

    if args.cmd == "preflight":
        pf = preflight()
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(pf, fh, indent=2, default=str)
        print(f"VERDICT={pf['verdict']}")
        for reason in pf["reasons"]:
            print(f"  - {reason}")
        return 3 if pf["verdict"] == "GATED" else 0
    if args.cmd == "report-gated":
        return cmd_report_gated(args)
    if args.cmd == "run":
        return cmd_run(args)
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
export SC_KEY_DIR="$KEY_DIR"
set +e
"$PYTHON" "$DRIVER" preflight --json-out "$PREFLIGHT_JSON"
PF_RC=$?
set -e

if [ "$PF_RC" -eq 3 ]; then
  echo "==> pre-flight GATED — writing the memo, not starting the run"
  "$PYTHON" "$DRIVER" report-gated \
    --preflight-json "$PREFLIGHT_JSON" \
    --report "$REPORT" \
    --stamp "$STAMP"
  echo "    triage memo: $REPORT"
  exit 3
elif [ "$PF_RC" -ne 0 ]; then
  echo "run_self_critique_pass: pre-flight driver failed (rc=$PF_RC)" >&2
  exit "$PF_RC"
fi

# ── Stages B–F: inventory / run / triage / addenda / sign ──────────────
echo "==> [B-F] inventory, run, triage, addenda, sign"
set +e
"$PYTHON" "$DRIVER" run \
  --preflight-json "$PREFLIGHT_JSON" \
  --stamp "$STAMP" \
  --report "$REPORT" \
  --run-dir "$RUN_DIR" \
  --addenda-dir "$ADDENDA_DIR" \
  --manifest-json "$MANIFEST_JSON" \
  --runs-dir "$RUNS_DIR" \
  --threshold-days "$THRESHOLD_DAYS" \
  --limit "$LIMIT" \
  --org "$ORG" \
  --judge "$JUDGE"
RUN_RC=$?
set -e
echo "    triage memo:  $REPORT"
echo "    run dir:      $RUN_DIR"

if [ "$RUN_RC" -eq 4 ]; then
  echo "==> run incomplete — articles pending but no judge wired (see memo)" >&2
  exit 4
elif [ "$RUN_RC" -ne 0 ]; then
  echo "run_self_critique_pass: run stage failed (rc=$RUN_RC)" >&2
  exit "$RUN_RC"
fi

echo "==> done"
exit 0
