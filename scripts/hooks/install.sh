#!/usr/bin/env bash
# Install the Theseus pre-commit hook into .git/hooks/pre-commit.
#
# Idempotent: re-running it overwrites the previous install but only
# if the file was placed by this script (it preserves an unrelated
# hand-written hook by refusing to overwrite without --force).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "install.sh: not inside a git repo" >&2
  exit 1
}

SOURCE="$REPO_ROOT/scripts/hooks/pre-commit.sh"
TARGET="$REPO_ROOT/.git/hooks/pre-commit"
MARKER="# theseus-pre-commit-shim"

if [ ! -f "$SOURCE" ]; then
  echo "install.sh: missing $SOURCE" >&2
  exit 1
fi

FORCE=0
if [ "${1:-}" = "--force" ]; then FORCE=1; fi

if [ -f "$TARGET" ] && ! grep -q "$MARKER" "$TARGET" 2>/dev/null; then
  if [ "$FORCE" -ne 1 ]; then
    echo "install.sh: refusing to overwrite existing $TARGET" >&2
    echo "  (it does not carry our marker — looks hand-written)." >&2
    echo "  Re-run with --force if you really want to replace it." >&2
    exit 2
  fi
fi

# Write a tiny shim. The shim exec's the tracked script under
# scripts/hooks/, so editing that file updates the behaviour without
# a reinstall.
cat > "$TARGET" <<EOF
#!/usr/bin/env bash
$MARKER
# Installed by scripts/hooks/install.sh. Edit scripts/hooks/pre-commit.sh
# (the tracked file) — this shim just exec's it.
REPO_ROOT="\$(git rev-parse --show-toplevel 2>/dev/null)"
exec "\$REPO_ROOT/scripts/hooks/pre-commit.sh" "\$@"
EOF
chmod +x "$TARGET"
chmod +x "$SOURCE"

echo "install.sh: installed pre-commit hook at $TARGET"
echo "install.sh: edits to scripts/hooks/pre-commit.sh take effect immediately."
