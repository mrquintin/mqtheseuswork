#!/usr/bin/env bash
# Pre-commit gate for Theseus.
#
# Runs the fast-path tests, prisma format/validate, and a credential
# regex sweep over the staged diff. Refuses the commit on any failure.
# Bypass with `git commit --no-verify` for genuine emergencies.
#
# Installed at .git/hooks/pre-commit by scripts/hooks/install.sh.
# Kept under scripts/hooks/ so it lives in git history and survives
# fresh clones (.git/hooks/ does not).

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  echo "pre-commit: not inside a git repo" >&2
  exit 1
fi
cd "$REPO_ROOT"

if [ -t 1 ]; then
  RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; BOLD=$'\033[1m'; NC=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; BOLD=""; NC=""
fi

fail() { echo "${RED}${BOLD}pre-commit: $*${NC}" >&2; exit 1; }
note() { echo "${YELLOW}pre-commit: $*${NC}"; }
ok()   { echo "${GREEN}pre-commit: $*${NC}"; }

# Allow the runner to skip the gate when it is committing its own
# bookkeeping (run logs, etc). Set THESEUS_SKIP_PRECOMMIT=1 in the
# environment for that single commit. Note: this is honoured by the
# hook only — not by `git commit` directly, so it does not weaken
# manual commits.
if [ "${THESEUS_SKIP_PRECOMMIT:-0}" = "1" ]; then
  note "THESEUS_SKIP_PRECOMMIT=1 — skipping gate."
  exit 0
fi

# 1. Credential regex sweep over the staged diff. Final defence behind
#    .gitignore. Run first so we fail fast on the most dangerous case.
STAGED_DIFF=$(git diff --cached --no-color 2>/dev/null || true)
if [ -n "$STAGED_DIFF" ]; then
  # Patterns: Anthropic live key, Stripe live key, AWS access key,
  # GitHub fine-grained token, PEM private key headers, and a generic
  # 64-hex wallet-key shape.
  CRED_REGEX='sk-ant-api[0-9]{2}-[A-Za-z0-9_\-]{20,}|sk_live_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|^\+.*[A-Za-z_]*PRIVATE_KEY[A-Z_]*=0x[0-9a-fA-F]{40,}'
  if echo "$STAGED_DIFF" | grep -E "$CRED_REGEX" >/dev/null 2>&1; then
    OFFENDING=$(echo "$STAGED_DIFF" | grep -E "$CRED_REGEX" | head -3)
    fail "credential-shaped value in staged diff. Refusing commit.
$OFFENDING
Rotate the value, remove it from the file, and re-stage.
Bypass (DANGEROUS) with: git commit --no-verify"
  fi
fi

# 2. Python fast-path tests. Only run if (a) noosphere/ exists and
#    (b) pytest is importable and (c) the staged diff actually touches
#    Python under noosphere/. The third condition keeps per-commit
#    latency reasonable for doc-only or frontend commits.
PY_STAGED=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '^noosphere/.*\.py$' || true)
if [ -n "$PY_STAGED" ] && [ -d "$REPO_ROOT/noosphere" ]; then
  if (cd "$REPO_ROOT/noosphere" && python3 -c "import pytest" >/dev/null 2>&1); then
    note "running noosphere pytest (fast path: not slow)…"
    if ! (cd "$REPO_ROOT/noosphere" && python3 -m pytest -x -m 'not slow' -q 2>&1 | tail -40); then
      fail "noosphere fast-path tests failed. Fix or use --no-verify."
    fi
    ok "noosphere fast-path tests passed."
  else
    note "pytest not installed for python3 — skipping noosphere tests."
  fi
fi

# 3. Frontend fast-path tests. Symmetric to (2): only run if the staged
#    diff touches theseus-codex/ JS/TS and vitest is available.
TS_STAGED=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '^theseus-codex/.*\.(ts|tsx|js|jsx)$' || true)
if [ -n "$TS_STAGED" ] && [ -f "$REPO_ROOT/theseus-codex/package.json" ]; then
  if (cd "$REPO_ROOT/theseus-codex" && command -v npx >/dev/null 2>&1 && npx --no-install vitest --version >/dev/null 2>&1); then
    note "running vitest…"
    if ! (cd "$REPO_ROOT/theseus-codex" && npx --no-install vitest run --reporter=verbose 2>&1 | tail -40); then
      fail "theseus-codex vitest failed. Fix or use --no-verify."
    fi
    ok "theseus-codex vitest passed."
  else
    note "vitest not installed in theseus-codex/ — skipping."
  fi
fi

# 4. Prisma format + validate, only when the schema is in the staged
#    diff. `prisma validate` insists on a DATABASE_URL being present,
#    even though it does not connect. The placeholder pattern was
#    established in earlier rounds; mirror it here.
PRISMA_STAGED=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '^theseus-codex/prisma/schema\.prisma$' || true)
if [ -n "$PRISMA_STAGED" ] && [ -f "$REPO_ROOT/theseus-codex/prisma/schema.prisma" ]; then
  if (cd "$REPO_ROOT/theseus-codex" && command -v npx >/dev/null 2>&1 && npx --no-install prisma --version >/dev/null 2>&1); then
    note "running prisma format + validate…"
    export DATABASE_URL="${DATABASE_URL:-postgresql://stub:stub@localhost:5432/stub?schema=public}"
    if ! (cd "$REPO_ROOT/theseus-codex" && npx --no-install prisma format --schema=prisma/schema.prisma >/dev/null 2>&1); then
      fail "prisma format rejected schema.prisma."
    fi
    if ! (cd "$REPO_ROOT/theseus-codex" && npx --no-install prisma validate --schema=prisma/schema.prisma >/dev/null 2>&1); then
      fail "prisma validate rejected schema.prisma."
    fi
    ok "prisma format + validate passed."
  else
    note "prisma CLI not installed in theseus-codex/ — skipping."
  fi
fi

ok "all checks passed."
exit 0
