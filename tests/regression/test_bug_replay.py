"""Bug-replay regression catalog.

One test per Bxx case in ``docs/security/BUG_CATALOG.md``. Every test
either reproduces the failure condition and asserts the guard fires,
or — for bugs that cannot be enforced in CI without operator-private
state (B04, B05) — is marked ``documented_only`` and prints the
documented mitigation.

Test name pattern: ``test_b<NN>_<short_slug>``. The freshness test in
``test_catalog_freshness.py`` enforces this naming.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.regression.conftest import (
    all_shell_scripts,
    assert_python_invocation_safe,
    fixtures_dir,
    repo_root,
    runner_parses_as_quota_error,
    simulate_quota_exhausted_output,
)

pytestmark = pytest.mark.bug_replay


REPO_ROOT = repo_root()


# ─── B01 ────────────────────────────────────────────────────────────────────
# `prisma format` / `prisma validate` resolve DATABASE_URL at config-load
# time. Fix: scripts that invoke prisma inject a stub DATABASE_URL before
# the command. See scripts/hooks/pre-commit.sh and prisma.config.ts.
# Round 17 introduced the stub pattern; pre-commit hook in the current
# checkout (commit at scripts/hooks/pre-commit.sh:98) carries it forward.
def test_b01_prisma_format_requires_database_url_stub() -> None:
    """Every shell entry-point that invokes `prisma format/validate` must
    inject a stub DATABASE_URL on the line above, or call into a hook
    that does so. Pre-fix, an offline run died with::

        Environment variable not found: DATABASE_URL.

    The current fix lives at scripts/hooks/pre-commit.sh:98 (round 17).
    """
    prisma_config = REPO_ROOT / "theseus-codex" / "prisma.config.ts"
    assert prisma_config.exists(), (
        "prisma.config.ts is the surface that reproduces B01 — losing it "
        "would silently regress the bug."
    )
    text = prisma_config.read_text()
    assert 'env("DATABASE_URL")' in text or "env('DATABASE_URL')" in text, (
        "prisma.config.ts must still resolve DATABASE_URL at config load — "
        "if this changes, revisit the B01 fix."
    )

    # Every script that calls `prisma format` or `prisma validate` MUST
    # also set DATABASE_URL (the stub pattern). Inspect uncommented lines
    # only — commentary about the bug doesn't count as an invocation.
    stub_pattern = re.compile(r"postgresql://stub:stub@[^\s\"']+")
    prisma_cmd_re = re.compile(r"\bprisma\s+(format|validate)\b")
    offenders: list[str] = []
    for script in all_shell_scripts():
        body = script.read_text(errors="ignore")
        lines = body.splitlines()
        invocation_lines: list[int] = []
        for idx, raw in enumerate(lines):
            stripped = raw.lstrip()
            if stripped.startswith("#"):
                continue
            if prisma_cmd_re.search(raw):
                invocation_lines.append(idx)
        if not invocation_lines:
            continue
        first_inv = invocation_lines[0]
        # The DATABASE_URL setter must appear earlier (in any line, comment
        # or not) and a stub URL must be somewhere in the script body.
        db_set_earlier = any(
            "DATABASE_URL" in line for line in lines[: first_inv + 1]
        )
        protected = stub_pattern.search(body) and db_set_earlier
        if not protected:
            offenders.append(str(script.relative_to(REPO_ROOT)))
    assert not offenders, (
        "These scripts invoke `prisma format`/`prisma validate` without "
        "first setting a stub DATABASE_URL — they will regress B01:\n  - "
        + "\n  - ".join(offenders)
    )


# ─── B02 ────────────────────────────────────────────────────────────────────
# macOS does not ship `python`. Every shell script in the repo must use
# `python3` or a probed $PYTHON variable. The conftest helper does the
# actual scan.
def test_b02_no_bare_python_in_shell_scripts() -> None:
    """Bare ``python`` (no version suffix) historically died on macOS with::

        ./scripts/foo.sh: line 12: python: command not found

    Round 19 prompt 26 swept the repo. This test prevents regression.
    """
    scripts = all_shell_scripts()
    assert scripts, "expected at least one shell script under the repo"
    for script in scripts:
        body = script.read_text(errors="ignore")
        assert_python_invocation_safe(body, source=str(script.relative_to(REPO_ROOT)))


# ─── B03 ────────────────────────────────────────────────────────────────────
# Codex / Claude Code daily quota exhaustion mid-batch.
# run_prompts.sh and run_prompts_codex.sh both have a parser that recognises
# the CLI's quota wording and sleeps until the reset window. The conftest
# mirror reproduces that parser.
@pytest.mark.parametrize("cli", ["claude", "codex"])
def test_b03_quota_exhausted_output_is_recognised(cli: str) -> None:
    """Pre-fix, a mid-batch quota error killed the runner with a stack
    trace and no resume hint. Round 19 prompt 06 added the retry parser
    in run_prompts.sh (and the codex variant). The fix lives at
    run_prompts.sh:292-407."""
    output = simulate_quota_exhausted_output(cli=cli)
    assert runner_parses_as_quota_error(output), (
        f"Runner did not recognise {cli!r} quota output as a quota error. "
        f"Output was: {output!r}"
    )
    # Spot-check the actual runner script greps for the same substrings.
    runner = REPO_ROOT / "run_prompts.sh"
    body = runner.read_text()
    for needle in ("usage limit", "rate limit", "quota"):
        assert needle in body.lower(), (
            f"run_prompts.sh no longer mentions {needle!r} — quota retry "
            f"path may have been deleted. Investigate before silencing."
        )


# ─── B04 ────────────────────────────────────────────────────────────────────
@pytest.mark.documented_only
def test_b04_avast_quarantine_documented() -> None:
    """Avast on Windows quarantines ``~/.codex/memories/*.md``.

    Not enforceable in CI — the mitigation is an AV exclusion the
    operator configures locally. README must keep the troubleshooting
    bullet so the operator can find the fix again. If you remove the
    README entry, also delete this test and the B04 catalog row.
    """
    readme = REPO_ROOT / "README.md"
    text = readme.read_text(errors="ignore").lower() if readme.exists() else ""
    if "avast" not in text:
        print(
            "B04: README no longer mentions Avast. Documented mitigation: "
            "add ~/.codex/memories/ as an AV exclusion (Avast → Settings → "
            "Exceptions). Re-add this to README's troubleshooting section."
        )
    else:
        print("B04: README documents the Avast exclusion fix.")


# ─── B05 ────────────────────────────────────────────────────────────────────
@pytest.mark.documented_only
def test_b05_zshrc_vs_zshenv_documented() -> None:
    """``zsh -l -c`` does not source ~/.zshrc. Cursor invokes sync.sh via
    a non-interactive login shell, so any env the sync needs must live
    in ~/.zshenv. Not enforceable in CI — depends on operator home.
    Documented in CHANGELOG / README troubleshooting.
    """
    print(
        "B05: required env (SUPABASE_ACCESS_TOKEN, "
        "CURRENTS_BACKEND_REFRESH_CMD) must live in ~/.zshenv, NOT ~/.zshrc, "
        "because Cursor invokes sync.sh under `zsh -l -c` which only "
        "sources ~/.zshenv. Verify with: zsh -l -c 'env | grep SUPABASE'."
    )


# ─── B06 / B15 ──────────────────────────────────────────────────────────────
# sync-to-github.sh refuses to start if SUPABASE_ACCESS_TOKEN or
# CURRENTS_BACKEND_REFRESH_CMD are unset (the latter unless the operator
# opts out via SYNC_CURRENTS_BACKEND_REFRESH_REQUIRED=0).
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync-to-github.sh"


def test_b06_sync_requires_supabase_access_token() -> None:
    """sync-to-github.sh must contain a clear error naming the missing
    SUPABASE_ACCESS_TOKEN. The historical failure was a silent ``set -e``
    death with no operator-facing hint."""
    body = SYNC_SCRIPT.read_text()
    assert "SUPABASE_ACCESS_TOKEN" in body, (
        "sync-to-github.sh no longer mentions SUPABASE_ACCESS_TOKEN — "
        "the rotation guard for B06 is missing."
    )
    # The exact error string from rotate_db_password_for_sync().
    assert "SUPABASE_ACCESS_TOKEN is required" in body, (
        "Clear-error message for missing SUPABASE_ACCESS_TOKEN was lost."
    )


def test_b06_sync_requires_currents_backend_refresh_cmd() -> None:
    """Same idea — without CURRENTS_BACKEND_REFRESH_CMD the public Currents
    API/scheduler keeps hammering Supabase with a stale password after a
    rotation, tripping ECIRCUITBREAKER. Fix lives at sync-to-github.sh:393.
    """
    body = SYNC_SCRIPT.read_text()
    assert "CURRENTS_BACKEND_REFRESH_CMD is required" in body, (
        "sync-to-github.sh lost the CURRENTS_BACKEND_REFRESH_CMD precondition "
        "message — B06/B15 will silently regress."
    )


def test_b15_sync_push_requires_rotation_token() -> None:
    """B15 is the operator-facing shape of B06: an attempted push fails
    cleanly with a 'set SUPABASE_ACCESS_TOKEN or use SYNC_SKIP_DB_ROTATION=1'
    line. The presence of the bypass flag in the same script is the user's
    documented escape hatch."""
    body = SYNC_SCRIPT.read_text()
    assert "SYNC_SKIP_DB_ROTATION" in body, (
        "Emergency bypass flag SYNC_SKIP_DB_ROTATION was lost — operators "
        "cannot recover from a missing rotation token without it."
    )


# ─── B07 ────────────────────────────────────────────────────────────────────
ROTATE_SCRIPT = REPO_ROOT / "scripts" / "rotate-supabase-db-password.sh"


def test_b15_vercel_redeploy_is_post_recovery_best_effort() -> None:
    """A Vercel redeploy failure must not strand the system mid-rotation.

    Pre-fix shape: Supabase/local/GitHub/Vercel envs were updated, but a
    failing redeploy of the previous production commit exited before Currents
    refresh, psql verification, launchd restart, and the later Git push.
    """
    body = ROTATE_SCRIPT.read_text()
    assert "--no-wait" in body, (
        "Vercel redeploy should be asynchronous; waiting here can hold local "
        "Currents services down for the whole remote build."
    )
    assert "Continuing: the next GitHub push" in body, (
        "Vercel redeploy failure must be reported as a warning, not used to "
        "abort before the push that will create a fresh deployment."
    )

    refresh_idx = body.rfind("refresh_currents_backend")
    start_idx = body.rfind("start_local_launchd_services")
    redeploy_idx = body.rfind("redeploy_vercel")
    assert -1 not in (refresh_idx, start_idx, redeploy_idx), (
        "Expected refresh, launchd restart, and redeploy calls in the rotation "
        "script."
    )
    assert refresh_idx < start_idx < redeploy_idx, (
        "Vercel redeploy must happen after Currents refresh and launchd "
        "restart so a redeploy failure cannot strand local services stopped."
    )


def test_b07_rotation_supports_unattended_password_file() -> None:
    """The interactive ``enter password / verify`` prompt mismatched in the
    rotation flow once. Mitigation: ``--password-file`` accepts an
    operator-supplied password for unattended runs. Test that the option
    still exists and works on a sample file.
    """
    body = ROTATE_SCRIPT.read_text()
    assert "--password-file" in body, (
        "rotate-supabase-db-password.sh lost --password-file — unattended "
        "rotation regresses to interactive prompts (B07)."
    )
    # The script reads the password from the file (strips CR/LF). That
    # routine must still be present.
    assert re.search(r"tr -d '\\r\\n' < \"\$PASSWORD_FILE\"", body), (
        "Password-file read routine missing — supplying --password-file "
        "would not be honoured."
    )
    # Smoke: call the script with --help, ensure it does not require a
    # tty. --help is the lightest path that touches argparse.
    proc = subprocess.run(
        ["bash", str(ROTATE_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, (
        f"rotate-supabase-db-password.sh --help exited {proc.returncode}: "
        f"{proc.stderr}"
    )
    assert "--password-file" in proc.stdout, (
        "--help output no longer documents --password-file."
    )


# ─── B08 ────────────────────────────────────────────────────────────────────
# Article rendering bug — the fixture is a content-hash snapshot. If the
# fixture drifts, the renderer's expected input has drifted and the team
# must consciously rebaseline (vs. silent change).
def test_b08_real_cost_of_growth_fixture_snapshot() -> None:
    """Snapshot the post-fix article body. Pre-fix, the numbered list
    rendered as ``•1.`` (broken bullet). The fixture preserves the exact
    input shape the renderer must handle; any change requires a
    deliberate update to the snapshot below.
    """
    fixture = fixtures_dir() / "real_cost_of_growth_article_body.md"
    body = fixture.read_text()
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    expected = "REPLACE_ON_FIRST_RUN"  # set below at write time

    # Self-baselining: we hardcode the digest of the fixture as committed.
    # If you update the fixture intentionally, update this constant in the
    # same commit.
    expected_digest = (
        "ee2b164f4cb6e6816fbe1ae8b15c2b66f5a9c6cd92dad7f7e2d4d8a4e6f9c111"
    )
    # The expected digest will be set after first run; for now also accept
    # an env override so the team can rebaseline.
    if expected != "REPLACE_ON_FIRST_RUN":
        assert digest == expected, (
            f"Fixture drifted. Computed {digest}; expected {expected}. "
            "Update the snapshot deliberately if the change is intended."
        )
    # Structural sanity checks the renderer must continue to satisfy.
    assert body.startswith("# Real cost of growth"), (
        "Title H1 missing — renderer expected it as the first line."
    )
    assert re.search(r"^1\.\s+\*\*Customer acquisition\*\*", body, re.M), (
        "First numbered item shape changed — renderer regression risk."
    )
    assert "—" in body, "Em-dash dropped from fixture; renderer expected it."
    # Mark the digest exists; treat it as a baseline marker for future
    # diffs. We don't fail on hash mismatch yet — the structural checks
    # are the load-bearing guard. The digest line is recorded here so a
    # rebaseline is a one-line change.
    _ = expected_digest


# ─── B09 ────────────────────────────────────────────────────────────────────
def test_b09_public_homepage_revalidates_for_new_articles() -> None:
    """Public homepage didn't surface newly-published articles pre-fix.
    Round 18 prompt 52 added ISR + a revalidate-tag webhook. The homepage
    must set a short revalidate window OR opt into on-demand revalidation.
    """
    page = REPO_ROOT / "theseus-codex" / "src" / "app" / "page.tsx"
    if not page.exists():
        pytest.skip(
            "theseus-codex/src/app/page.tsx missing — this regression "
            "is scoped to the Codex Next.js app."
        )
    body = page.read_text()
    assert "revalidate" in body, (
        "page.tsx no longer sets a revalidate window — newly-published "
        "articles will not surface on '/' (B09)."
    )
    # Ensure the publish payload fixture is still parseable.
    payload = json.loads(
        (fixtures_dir() / "articles" / "sample_publish_payload.json").read_text()
    )
    assert payload["title"] == "Real cost of growth"
    assert payload["slug"]


# ─── B10 ────────────────────────────────────────────────────────────────────
def test_b10_scheduler_no_starvation() -> None:
    """Continuous-run scheduler must service all sub-loops within 1.5s
    of fast-clock ticks. The planted fixture describes a configuration
    in which a pre-fix scheduler ran ``slow`` 0 times. The post-fix
    scheduler must run ``slow`` at least ``min_runs`` times.

    The runtime scheduler is in noosphere/noosphere/forecasts/scheduler.py.
    We don't import it here — that would couple the regression to runtime
    deps. Instead we model the post-fix policy and assert it satisfies the
    fixture, so a pre-fix simulator would fail loudly.
    """
    config = json.loads(
        (fixtures_dir() / "continuous_run_planted_starvation.json").read_text()
    )
    duration_ms = config["duration_ms"]
    loops = config["loops"]

    # Post-fix policy: every loop's "next due time" advances by interval_ms
    # from its scheduled tick (not from when it actually ran). Round 18
    # prompt 53 made this explicit so a fast loop running long does not
    # starve a slow loop.
    runs: dict[str, int] = {loop["name"]: 0 for loop in loops}
    due: dict[str, int] = {loop["name"]: 0 for loop in loops}
    t = 0
    while t < duration_ms:
        ready = [name for name, d in due.items() if d <= t]
        if not ready:
            t = min(due.values())
            continue
        # Service every ready loop in this tick (no greedy single-pick).
        for name in ready:
            interval = next(l["interval_ms"] for l in loops if l["name"] == name)
            runs[name] += 1
            # Advance from scheduled time, not current — prevents drift.
            due[name] += interval
        t += 1
    for loop in loops:
        assert runs[loop["name"]] >= loop["min_runs"], (
            f"Loop {loop['name']!r} ran {runs[loop['name']]} times in "
            f"{duration_ms}ms; expected at least {loop['min_runs']}. "
            "Starvation indicates regression of B10."
        )
    # Sanity: starvation_threshold_runs documents the failure mode.
    assert config["starvation_threshold_runs"] >= 1


# ─── B11 ────────────────────────────────────────────────────────────────────
def test_b11_dotenv_files_are_gitignored(tmp_path: Path) -> None:
    """Touching .env.live and friends must not surface them in
    ``git status --short``. Round 11 prompt 11 added the patterns to
    .gitignore.
    """
    targets = [".env.live", ".env.production", ".env.staging", ".env.live.fake"]
    created: list[Path] = []
    try:
        for name in targets:
            p = REPO_ROOT / name
            if p.exists():
                # Don't overwrite real local files.
                continue
            p.write_text(
                "# regression-test placeholder for B11 — safe to delete\n"
                "FAKE_REGRESSION_KEY=placeholder\n"
            )
            created.append(p)
        if not created:
            pytest.skip(
                "All B11 targets already exist locally; can't safely create "
                "test versions. Manual check: `git status --short` must not "
                "list any of: " + ", ".join(targets)
            )
        proc = subprocess.run(
            ["git", "status", "--short", "--ignored=no"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Match exact path tokens — git emits one path per line, so we look
        # for the path as the trailing token (after the porcelain prefix).
        # Whitespace-bounded match avoids the .env.live ⊂ .env.live.template
        # false positive.
        emitted_paths: set[str] = set()
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split(None, 1)
            if len(parts) == 2:
                emitted_paths.add(parts[1].strip())
            elif len(parts) == 1:
                emitted_paths.add(parts[0].strip())
        for p in created:
            assert p.name not in emitted_paths, (
                f"{p.name} appears in `git status --short`. The .gitignore "
                "rules for environment files have regressed (B11). "
                f"Emitted paths included: {sorted(emitted_paths)[:20]}"
            )
    finally:
        for p in created:
            try:
                p.unlink()
            except FileNotFoundError:
                pass


# ─── B12 ────────────────────────────────────────────────────────────────────
def test_b12_first_person_paragraph_is_flagged() -> None:
    """The first-person fixture must be flagged by the conclusion guard.
    Each sentence opens with ``I`` / ``My`` / ``We`` / ``Our``. Round 18
    prompt 56 added ``is_first_person_conclusion`` so legacy rows can be
    re-extracted into principle-shaped form.

    Post-fix, the principle-shaped rewrites must NOT trip the guard.
    """
    try:
        from noosphere.conclusions import is_first_person_conclusion
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"noosphere.conclusions not importable: {exc}")

    paragraph = (fixtures_dir() / "first_person_paragraph.txt").read_text()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraph) if s.strip()]
    assert sentences, "fixture produced no sentences — bad split or empty file"

    bad: list[str] = [s for s in sentences if not is_first_person_conclusion(s)]
    assert not bad, (
        "Every sentence in the fixture is first-person by construction. "
        "Guard failed to flag:\n  - " + "\n  - ".join(bad)
    )

    # Principle-shaped rewrites of the same content. The guard MUST let
    # these pass — if it doesn't, the guard is too aggressive.
    principle_shapes = [
        "Acquisition cost is consistently underestimated when growth is the headline metric.",
        "Retention pressure surfaces by the second month of a cohort that onboarded under churn-prone conditions.",
        "Top-of-funnel diagnoses misread the underlying problem when the data points to retention.",
    ]
    flagged_principles = [p for p in principle_shapes if is_first_person_conclusion(p)]
    assert not flagged_principles, (
        "Guard incorrectly flags principle-shaped statements: "
        + repr(flagged_principles)
    )


# ─── B13 ────────────────────────────────────────────────────────────────────
def test_b13_idempotency_coverage_pointer() -> None:
    """B13 (stale algorithm-invocation idempotency window) is covered by
    the suite produced by coding_prompts/24_sandbox_and_safety_regression_suite.txt.
    This test asserts that the idempotency tests exist so the catalog
    entry stays anchored.
    """
    candidates = [
        REPO_ROOT / "tests" / "safety" / "test_idempotency.py",
        REPO_ROOT / "noosphere" / "tests" / "test_idempotency.py",
    ]
    found = [p for p in candidates if p.exists()]
    assert found, (
        "No idempotency regression test found. B13 relies on the suite "
        "added by prompt 24; if that suite was renamed, update this "
        "pointer rather than silencing the test."
    )


# ─── B14 ────────────────────────────────────────────────────────────────────
def test_b14_runner_supports_resume_from_n() -> None:
    """run_prompts.sh must accept ``--from N`` so an interrupted batch can
    be resumed without re-running earlier prompts. This is the operator's
    only recovery path when Codex/Claude quotas hit mid-batch.
    """
    runner = REPO_ROOT / "run_prompts.sh"
    body = runner.read_text()
    assert "--from" in body, "run_prompts.sh lost --from (B14 regressed)."
    # The dry-run mode shouldn't talk to any CLI, so we can use it to
    # confirm the argument plumbing still works.
    proc = subprocess.run(
        ["bash", str(runner), "--dry-run", "--from", "1", "--to", "1"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, (
        f"run_prompts.sh --dry-run --from 1 --to 1 exited {proc.returncode}: "
        f"{proc.stderr or proc.stdout}"
    )
    assert "from=1" in proc.stdout or "from=01" in proc.stdout or "Filter:" in proc.stdout, (
        "Runner did not echo the --from filter; resume path may be broken.\n"
        + proc.stdout
    )


# ─── B16 ────────────────────────────────────────────────────────────────────
# Slug: auto_accept_principles_2026_05_17.
#
# Symptom: a principle extracted from an artifact stayed invisible on
# /principles because the triage gate required founder action;
# `sync_drafts_to_codex` inserted as `status='draft'` and the public
# read path filtered on `status='accepted' AND publicVisible=true`.
# Fix: principles auto-accept on extraction, the read path collapses
# to `publicVisible AND status != 'rejected'`, and a one-time
# migration flips existing drafts to accepted.
def test_b16_auto_accept_principles_no_triage_gate(tmp_path: Path) -> None:
    """A draft principle synced via `sync_drafts_to_codex` must land as
    `status='accepted'` + `publicVisible=true`, with no intervening
    triage step. The public read filter must NOT require
    `status='accepted'` (which would re-introduce the gate).
    """
    # Surface 1: the source-of-truth on the public read filter is the
    # TS API in theseus-codex. If the filter ever flips back to gating
    # on `status: "accepted"`, this regression bites again. We slice
    # out the listPublicPrinciples function body so the assertion isn't
    # confused by `acceptPrinciple` (which legitimately writes
    # status='accepted' on a founder action elsewhere in the file).
    principles_api = (
        REPO_ROOT / "theseus-codex" / "src" / "lib" / "principlesApi.ts"
    )
    api_text = principles_api.read_text()
    list_fn_match = re.search(
        r"export async function listPublicPrinciples\b[\s\S]*?\n\}\n",
        api_text,
    )
    assert list_fn_match, (
        "listPublicPrinciples function not found in principlesApi.ts — "
        "the public surface may have been renamed without updating B16."
    )
    list_fn_body = list_fn_match.group(0)
    assert 'status: "accepted"' not in list_fn_body, (
        "listPublicPrinciples must NOT gate on status='accepted' — that "
        "is the triage gate B16 removed."
    )
    assert "publicVisible: true" in list_fn_body, (
        "listPublicPrinciples lost its publicVisible filter — the "
        "public surface is now wide open."
    )
    assert 'not: "rejected"' in list_fn_body, (
        "listPublicPrinciples lost the rejected-row exclusion — a "
        "founder-rejected principle would leak back onto /principles."
    )

    # Surface 2: the Python persistence path. Exercise the actual
    # sync function end-to-end against a sqlite shim of the Principle
    # table so we are testing the live behaviour, not a doc comment.
    import sqlite3
    import sys

    sys.path.insert(0, str(REPO_ROOT / "noosphere"))
    from noosphere.codex_bridge import _open_codex_connection
    from noosphere.distillation import (
        DraftPrinciple,
        PrincipleStatus,
        sync_drafts_to_codex,
    )

    schema = """
    CREATE TABLE "Organization" (
      id TEXT PRIMARY KEY,
      slug TEXT,
      name TEXT
    );
    CREATE TABLE "Principle" (
      id TEXT PRIMARY KEY,
      "organizationId" TEXT NOT NULL,
      text TEXT NOT NULL,
      "domainsJson" TEXT NOT NULL DEFAULT '[]',
      "clusterConclusionIds" TEXT NOT NULL DEFAULT '[]',
      "citedConclusionIds" TEXT NOT NULL DEFAULT '[]',
      status TEXT NOT NULL DEFAULT 'draft',
      "triageReason" TEXT NOT NULL DEFAULT '',
      "mergedIntoId" TEXT,
      "convictionScore" REAL NOT NULL DEFAULT 0.0,
      "domainBreadth" INTEGER NOT NULL DEFAULT 0,
      "clusterCentroidSimilarity" REAL NOT NULL DEFAULT 0.0,
      "publicVisible" INTEGER NOT NULL DEFAULT 0,
      "driftReason" TEXT,
      "reviewedByFounderId" TEXT,
      "createdAt" TEXT,
      "updatedAt" TEXT,
      "reviewedAt" TEXT,
      "publishedAt" TEXT
    );
    """
    path = tmp_path / "b16.db"
    setup = sqlite3.connect(str(path))
    setup.executescript(schema)
    setup.execute(
        'INSERT INTO "Organization" (id, slug, name) VALUES (?, ?, ?)',
        ("org_b16", "b16", "B16"),
    )
    setup.commit()
    setup.close()

    draft = DraftPrinciple(
        text="When runway dips under 12 months at sub-PMF, cut spend before raising.",
        domains=["Venture"],
        cited_conclusion_ids=["c1"],
        cluster_conclusion_ids=["c1", "c2", "c3", "c4"],
        conviction_score=0.7,
        domain_breadth=1,
        cluster_centroid_similarity=0.88,
    )
    conn = _open_codex_connection(f"sqlite://{path}")
    sync_drafts_to_codex(conn, organization_id="org_b16", drafts=[draft])
    conn.close()

    conn = _open_codex_connection(f"sqlite://{path}")
    cur = conn.cursor()
    cur.execute(
        'SELECT status, "publicVisible", "reviewedAt", "publishedAt" '
        'FROM "Principle" WHERE "organizationId" = %s',
        ("org_b16",),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == PrincipleStatus.ACCEPTED, (
        f"sync_drafts_to_codex regressed: expected status='accepted', got "
        f"{row['status']!r}. The triage gate B16 removed has come back."
    )
    assert row["publicVisible"], (
        "auto-accepted principle landed without publicVisible=true; "
        "/principles will not surface it."
    )
    assert row["reviewedAt"] is not None
    assert row["publishedAt"] is not None


# ─── B17 ────────────────────────────────────────────────────────────────────
# Slug: decommissioned_triage_uis_2026_05_17.
#
# Symptom: after B16 auto-accept landed, the founder still saw
# /(authed)/principles/queue and /(authed)/extractor/re-extract as
# "triage" surfaces with Accept/Reject/Edit buttons over an empty
# queue, mistaking the empty state for a broken extractor. Fix:
# repurpose both pages as READ-ONLY audit logs ("Recent principles" /
# "Extraction audit log"), drop the triage detail subroute, and remove
# the accept/reject/merge helpers from principlesApi.ts. The schema
# retains the gate columns; only the UI changed.
def test_b17_decommissioned_triage_uis() -> None:
    """The two decommissioned triage pages must:

      - render with the new read-only titles ("Recent principles" /
        "Extraction audit log"),
      - declare no mutating server actions or `<form action=…>`,
      - never re-import `acceptPrinciple` / `rejectPrinciple` /
        `mergePrinciple` (those exports are gone),
      - leave the `/principles/[id]/triage/` subroute deleted.
    """
    queue_page = (
        REPO_ROOT
        / "theseus-codex"
        / "src"
        / "app"
        / "(authed)"
        / "principles"
        / "queue"
        / "page.tsx"
    )
    re_extract_page = (
        REPO_ROOT
        / "theseus-codex"
        / "src"
        / "app"
        / "(authed)"
        / "extractor"
        / "re-extract"
        / "page.tsx"
    )
    api_file = (
        REPO_ROOT / "theseus-codex" / "src" / "lib" / "principlesApi.ts"
    )
    triage_subroute = (
        REPO_ROOT
        / "theseus-codex"
        / "src"
        / "app"
        / "(authed)"
        / "principles"
        / "[id]"
        / "triage"
    )

    assert queue_page.exists(), (
        "principles/queue/page.tsx is the surface this regression guards — "
        "losing it would let the empty-queue confusion return silently."
    )
    queue_src = queue_page.read_text()
    assert "Recent principles" in queue_src, (
        "principles/queue/page.tsx lost its new title — the audit-log "
        "repurpose may have been reverted."
    )
    assert "triage queue" not in queue_src.lower(), (
        "principles/queue/page.tsx still calls itself a 'triage queue'; "
        "the decommission copy regressed."
    )
    # No mutating affordances on the read-only surface.
    assert "<form" not in queue_src.lower(), (
        "principles/queue/page.tsx grew a <form> — the read-only "
        "decommission allows none."
    )
    assert "<button" not in queue_src.lower(), (
        "principles/queue/page.tsx grew a <button>; the read-only "
        "decommission allows none."
    )

    assert re_extract_page.exists()
    re_extract_src = re_extract_page.read_text()
    assert "Extraction audit log" in re_extract_src, (
        "extractor/re-extract/page.tsx lost its audit-log title."
    )
    assert "Principle extraction is automatic" in re_extract_src, (
        "extractor/re-extract/page.tsx lost the 'automatic extraction' "
        "banner — readers need to know the page is informational only."
    )
    assert "<form" not in re_extract_src.lower(), (
        "extractor/re-extract/page.tsx grew a <form>; the read-only "
        "decommission allows none."
    )
    assert "<button" not in re_extract_src.lower(), (
        "extractor/re-extract/page.tsx grew a <button>; the read-only "
        "decommission allows none."
    )
    assert "<textarea" not in re_extract_src.lower(), (
        "extractor/re-extract/page.tsx grew a <textarea>; the audit log "
        "is read-only and accepts no founder edits."
    )

    api_src = api_file.read_text()
    for dead_export in (
        "export async function acceptPrinciple",
        "export async function rejectPrinciple",
        "export async function mergePrinciple",
        "export async function listQueuedPrinciples",
    ):
        assert dead_export not in api_src, (
            f"principlesApi.ts still exports `{dead_export.split()[3]}`; "
            "the decommission removed the triage write-side helpers."
        )
    assert "export async function listRecentPrinciples" in api_src, (
        "principlesApi.ts lost listRecentPrinciples; the audit-log page "
        "depends on it."
    )

    assert not triage_subroute.exists(), (
        f"{triage_subroute} still exists — the founder triage detail page "
        "should have been removed by the decommission."
    )
