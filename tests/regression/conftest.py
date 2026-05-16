"""Shared helpers for the bug-replay regression catalog.

Helpers are CLI-agnostic — the runner uses the Claude Code CLI today,
but the bug catalog documents historical Codex CLI failure modes too
because the same shapes can recur on either side. Tests that need a
quota-exhaustion or auth-failure shape ask for it by ``cli=...`` and
get the right textual signature.

This module also exposes the canonical pytest marker
``documented_only`` for bugs (B04, B05) that cannot be enforced in CI
without access to the operator's home directory or AV configuration.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
REGRESSION_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = REGRESSION_DIR / "fixtures"


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers this suite uses so ``--strict-markers`` is happy."""
    config.addinivalue_line(
        "markers",
        "documented_only: regression that is documented (e.g. in README) "
        "but cannot be enforced in CI without operator-private state.",
    )
    config.addinivalue_line(
        "markers",
        "bug_replay: belongs to the canonical bug-replay catalog "
        "(docs/security/BUG_CATALOG.md). Every Bxx entry MUST have one.",
    )


# ---------------------------------------------------------------------------
# Quota exhaustion fixtures for B03.
# ---------------------------------------------------------------------------
# These strings mirror the actual JSONL/text emitted by each CLI when its
# subscription hits the daily quota. run_prompts.sh's parser grep'es for these
# substrings to decide whether to sleep+retry vs. fail loudly. If either CLI
# changes its wording, the parser AND this fixture move together.

_QUOTA_OUTPUTS = {
    "claude": (
        '{"type":"error","subtype":"usage_limit_exceeded",'
        '"message":"Claude AI usage limit reached. '
        'Your limit will reset at Jan 24, 2026 3:00 PM. '
        'Try again at Jan 24, 2026 3:00 PM."}'
    ),
    "codex": (
        "ERROR: You have reached your Codex usage limit. "
        "Quota exceeded. Try again at Jan 24, 2026 3:00 PM."
    ),
}


def simulate_quota_exhausted_output(cli: str = "claude") -> str:
    """Return a realistic quota-exhaustion log line for ``cli``.

    The regression test for B03 feeds the output to the runner's parser and
    asserts that the parser (a) recognises it as a quota error, and (b)
    extracts a reset-epoch in the future.
    """
    try:
        return _QUOTA_OUTPUTS[cli]
    except KeyError as exc:
        raise ValueError(
            f"unknown cli {cli!r}; expected one of {sorted(_QUOTA_OUTPUTS)}"
        ) from exc


# ---------------------------------------------------------------------------
# Shell-script linting helpers for B02.
# ---------------------------------------------------------------------------
# macOS does not ship a `python` binary by default — only `python3`. A bare
# `python` in a shell script will silently break on the operator's machine
# (or, worse, find a stray homebrew `python` and run with a different env).
# Acceptable forms:
#   * `python3 …`
#   * `"$PYTHON" …` where PYTHON has been resolved via a `command -v` probe
#   * `./.venv/.../bin/python …` (project venv path; absolute)
#   * `$VENV/bin/python …` or `${VENV}/bin/python …`
#   * inside heredocs that are obviously NOT shell-executed (e.g. node/python
#     code blocks). The check is intentionally line-scoped; multi-line
#     heredocs are out of scope.

_BARE_PYTHON_PATTERN = re.compile(
    r"(?<![\w./$\"'-])python(?![\w./0-9])"  # whole-word `python`, no version suffix
)


def _line_is_bare_python_invocation(line: str) -> bool:
    """True if the line begins (after optional whitespace and shell prefixes)
    with a bare ``python`` command that could fail on macOS."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    # Allow `python3`, project venv paths, and `$VAR/bin/python` style refs.
    if not _BARE_PYTHON_PATTERN.search(stripped):
        return False
    # Tokenise so we only flag `python` when it's at the head of a command,
    # not buried inside `--description "python3 wrapper"`.
    try:
        tokens = shlex.split(stripped, comments=True, posix=True)
    except ValueError:
        # Unbalanced quotes — fall back to the raw regex hit; safer to flag.
        return True
    if not tokens:
        return False
    # Walk left-to-right; the head of every command is the first token after
    # `;`, `&&`, `||`, `|`, or the start of the line.
    cmd_heads: list[str] = []
    next_is_head = True
    for tok in tokens:
        if tok in {";", "&&", "||", "|", "&"}:
            next_is_head = True
            continue
        if next_is_head:
            # Strip env-var assignments at the head: `FOO=bar python ...`
            if "=" in tok and tok.split("=", 1)[0].isidentifier():
                continue
            cmd_heads.append(tok)
            next_is_head = False
    return any(_BARE_PYTHON_PATTERN.fullmatch(head) for head in cmd_heads)


def _toggle_double_quote_state(line: str, *, start: bool) -> bool:
    """Return whether we end this line inside an open double-quoted string.

    Crude — counts unescaped `"` characters. Single quotes do not toggle
    (they are stronger in POSIX shell). `start` indicates whether the
    line BEGAN inside a quoted string; ignored beyond toggling.
    """
    open_quote = start
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            i += 2
            continue
        if c == "'" and not open_quote:
            # Skip single-quoted segment.
            j = line.find("'", i + 1)
            i = (j + 1) if j != -1 else len(line)
            continue
        if c == '"':
            open_quote = not open_quote
        i += 1
    return open_quote


def assert_python_invocation_safe(snippet: str, *, source: str = "<snippet>") -> None:
    """Raise AssertionError if ``snippet`` has a bare ``python`` invocation.

    Used by the B02 regression to lint every shell script the repo ships.
    Tracks open double-quoted strings across lines so that a ``python``
    word inside an instruction message (e.g. a multi-line ``fail "…"`` arg)
    is not flagged.
    """
    offenders: list[tuple[int, str]] = []
    in_double_quote = False
    in_heredoc: str | None = None  # closing delimiter when inside a heredoc
    for lineno, raw in enumerate(snippet.splitlines(), start=1):
        # Heredoc handling: anything between `<<EOF` and a line containing
        # just `EOF` is non-shell content and never counts as a command.
        if in_heredoc is not None:
            if raw.strip() == in_heredoc:
                in_heredoc = None
            continue
        heredoc_open = re.search(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?", raw)
        if heredoc_open and not raw.lstrip().startswith("#"):
            in_heredoc = heredoc_open.group(1)
            # The heredoc starter line itself may have a command before <<;
            # but for our lint we only care about command heads on a line,
            # and `python …` followed by `<< EOF` would have been caught
            # already.
        # Skip the line entirely if we entered this line already inside a
        # quoted string (continuation of a multi-line shell string).
        if in_double_quote:
            # Update quote state by counting unescaped quotes on this line.
            in_double_quote = _toggle_double_quote_state(raw, start=True)
            continue
        if _line_is_bare_python_invocation(raw):
            offenders.append((lineno, raw.rstrip()))
        in_double_quote = _toggle_double_quote_state(raw, start=False)
    if offenders:
        report = "\n".join(f"  {source}:{n}: {line}" for n, line in offenders)
        raise AssertionError(
            "Bare `python` invocation found (macOS ships only `python3` by "
            "default — use `python3` or a probed $PYTHON variable):\n" + report
        )


# ---------------------------------------------------------------------------
# Quota-output parser (B03) — mirrors run_prompts.sh's quota detector.
# ---------------------------------------------------------------------------
# The shell parser is in run_prompts.sh; this Python mirror lets the
# regression test exercise the same logic from pytest. Both must agree on
# what counts as a quota signal.

_QUOTA_DETECT_RE = re.compile(
    r"usage limit|rate limit|quota exceeded|too many requests"
    r"|quota reached|reached your.* limit",
    re.IGNORECASE,
)


def runner_parses_as_quota_error(output: str) -> bool:
    return bool(_QUOTA_DETECT_RE.search(output))


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def repo_root() -> Path:
    return REPO_ROOT


def fixtures_dir() -> Path:
    return FIXTURES_DIR


def all_shell_scripts() -> list[Path]:
    """Operator-facing shell scripts — the surface where B02 actually hit.

    The bug surfaced on the operator's Mac running scripts from the repo
    root (sync.sh, run_prompts.sh) or `scripts/`. Research/benchmark
    shell scripts buried under sub-packages (e.g. ``noosphere/scripts/``)
    target a Linux research environment and are out of scope for the
    macOS-specific regression. If one of those sub-package scripts later
    becomes operator-facing, move it up to top-level ``scripts/``.
    """
    out: list[Path] = []
    # Top-level *.sh files at the repo root.
    for path in REPO_ROOT.glob("*.sh"):
        if path.is_file():
            out.append(path)
    # Everything under top-level scripts/ (recursive — hooks, smoke, etc.).
    scripts_dir = REPO_ROOT / "scripts"
    if scripts_dir.is_dir():
        for path in scripts_dir.rglob("*.sh"):
            if path.is_file():
                out.append(path)
        # Extensionless bash entrypoints under scripts/.
        for path in scripts_dir.iterdir():
            if path.suffix == "" and path.is_file():
                try:
                    head = path.read_bytes()[:80]
                except OSError:
                    continue
                if head.startswith(b"#!") and b"sh" in head.split(b"\n", 1)[0]:
                    out.append(path)
    return sorted(set(out))


# ---------------------------------------------------------------------------
# Tiny xfail/skip helpers
# ---------------------------------------------------------------------------
def under_ci() -> bool:
    return any(os.environ.get(k) for k in ("CI", "GITHUB_ACTIONS"))
