#!/usr/bin/env bash
# Build a tenant-installable Theseus template from this source repo.
#
# Reads `scripts/template/manifest.yml` and writes a clean output
# directory (default: `../theseus-template/`). The output is a
# brand-new git repo with a single initial commit.
#
# Re-running the script is idempotent: same source tree → byte-
# identical output (modulo file timestamps, which are not asserted).
#
# Usage:
#   scripts/build_template.sh                       # writes to ../theseus-template
#   scripts/build_template.sh --dest /tmp/out       # custom output dir
#   scripts/build_template.sh --src /path/to/src    # custom source repo
#   scripts/build_template.sh --no-git              # skip the git init / initial commit
#   scripts/build_template.sh --manifest path.yml   # custom manifest
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SRC="$(cd "$SCRIPT_DIR/.." && pwd)"

SRC="$DEFAULT_SRC"
DEST=""
MANIFEST=""
DO_GIT=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src) SRC="$2"; shift 2 ;;
    --dest) DEST="$2"; shift 2 ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    --no-git) DO_GIT=0; shift ;;
    -h|--help)
      sed -n '2,17p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

SRC="$(cd "$SRC" && pwd)"
if [[ -z "$MANIFEST" ]]; then
  MANIFEST="$SRC/scripts/template/manifest.yml"
fi
if [[ ! -f "$MANIFEST" ]]; then
  echo "manifest not found: $MANIFEST" >&2
  exit 2
fi

# Resolve default destination from the manifest if not provided on the CLI.
if [[ -z "$DEST" ]]; then
  DEST_REL="$(python3 - "$MANIFEST" <<'PY'
import sys, yaml
with open(sys.argv[1]) as fh:
    m = yaml.safe_load(fh)
print(m.get("output", {}).get("default_dir", "../theseus-template"))
PY
)"
  case "$DEST_REL" in
    /*) DEST="$DEST_REL" ;;
    *)  DEST="$(cd "$SRC" && cd "$(dirname "$DEST_REL")" 2>/dev/null && pwd)/$(basename "$DEST_REL")"
        if [[ -z "$DEST" || "$DEST" == "/$(basename "$DEST_REL")" ]]; then
          DEST="$SRC/$DEST_REL"
        fi
        ;;
  esac
fi

echo "[build_template] src=$SRC"
echo "[build_template] dest=$DEST"
echo "[build_template] manifest=$MANIFEST"

# Refuse to write into the source repo itself.
case "$DEST" in
  "$SRC"|"$SRC"/*)
    echo "refusing to write template inside source repo: $DEST" >&2
    exit 2
    ;;
esac

# Clean output directory.
if [[ -e "$DEST" ]]; then
  rm -rf "$DEST"
fi
mkdir -p "$DEST"

# Hand off to the Python worker that walks the manifest. Keeping the
# heavy lifting in Python lets the bash wrapper stay readable while
# we still satisfy the prompt's "scripts/build_template.sh" entry
# point. The worker is embedded so the script is self-contained.
SRC="$SRC" DEST="$DEST" MANIFEST="$MANIFEST" python3 - <<'PY'
import fnmatch
import json
import os
import re
import shutil
import sys
from pathlib import Path

import yaml

SRC = Path(os.environ["SRC"]).resolve()
DEST = Path(os.environ["DEST"]).resolve()
MANIFEST = Path(os.environ["MANIFEST"]).resolve()

with MANIFEST.open() as fh:
    manifest = yaml.safe_load(fh)

CORE = manifest.get("include_core", []) or []
CONFIG = manifest.get("include_config", []) or []
SEED = manifest.get("include_seed", []) or []
SEED_STUBS = manifest.get("seed_stubs", {}) or {}
EXCLUDE_FIRM = manifest.get("exclude_firm", []) or []
EXCLUDE_GLOBS = manifest.get("exclude_globs", []) or []
TOKENS = manifest.get("tokens", {}) or {}
FORBIDDEN = manifest.get("forbidden_phrases", []) or []
PAYLOAD = manifest.get("payload", []) or []


def norm(entry: str) -> str:
    return entry.rstrip("/")


def is_dir_entry(entry: str) -> bool:
    return entry.endswith("/")


def src_path(entry: str) -> Path:
    return SRC / norm(entry)


def matches_glob_any(rel_path: str, patterns) -> bool:
    for pat in patterns:
        pat = pat.rstrip("/")
        if fnmatch.fnmatch(rel_path, pat):
            return True
        if fnmatch.fnmatch(rel_path, pat + "/*"):
            return True
        # ** glob support — fnmatch does substring matching when **/x is used
        if "**" in pat:
            simple = pat.replace("**/", "")
            if fnmatch.fnmatch(rel_path, simple) or fnmatch.fnmatch(os.path.basename(rel_path), simple):
                return True
        # directory contained match: "foo/" should match "foo/bar"
        if "/" in pat or pat in rel_path.split(os.sep):
            parts = rel_path.split(os.sep)
            target = pat.split("/")[-1]
            if target and target in parts:
                return True
    return False


def is_excluded_firm(rel: str) -> bool:
    for entry in EXCLUDE_FIRM:
        e = norm(entry)
        if rel == e:
            return True
        if rel.startswith(e + os.sep):
            return True
    return False


def is_excluded_glob(rel: str) -> bool:
    return matches_glob_any(rel, EXCLUDE_GLOBS)


def is_excluded(rel: str) -> bool:
    return is_excluded_firm(rel) or is_excluded_glob(rel)


FORBIDDEN_PLACEHOLDER = "[firm-specific reference redacted]"


def apply_tokens(text: str) -> str:
    for key, spec in TOKENS.items():
        src_val = spec.get("source_value")
        tmpl_val = spec.get("template_value")
        if src_val is None or tmpl_val is None:
            continue
        # Plain string replacement (covers both literal `THESEUS_ORG_NAME`
        # references and any source-value occurrences).
        text = text.replace(key, tmpl_val) if key in text else text
        text = text.replace(src_val, tmpl_val)
    # Scrub any forbidden firm-attribution phrases that survived token
    # substitution. We replace with a neutral placeholder so the surrounding
    # structure (bibtex entries, prose) remains intact for the tenant to
    # repopulate. The final pass after the whole copy then asserts that
    # nothing slipped through.
    for phrase in FORBIDDEN:
        if phrase in text:
            text = text.replace(phrase, FORBIDDEN_PLACEHOLDER)
    return text


def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            chunk = fh.read(4096)
        if not chunk:
            return False
        if b"\x00" in chunk:
            return True
        # Heuristic: if more than 30% of bytes are non-printable, treat as binary.
        text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x7F)))
        nontext = sum(1 for b in chunk if b not in text_chars)
        return (nontext / len(chunk)) > 0.30
    except OSError:
        return False


PDF_KEEP = {"docs/guides"}


def keep_pdf(rel: str) -> bool:
    for keep in PDF_KEEP:
        if rel.startswith(keep + os.sep) or rel == keep:
            return True
    return False


def copy_file(src: Path, dst: Path, *, transform=False, check_forbidden=False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if is_binary(src):
        # PDFs that survived the inclusion list are only the prompt-67 guides.
        if src.suffix.lower() == ".pdf":
            rel = str(src.relative_to(SRC)) if src.is_relative_to(SRC) else src.name
            if not keep_pdf(rel):
                return
        shutil.copy2(src, dst)
        return
    try:
        text = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        shutil.copy2(src, dst)
        return
    if transform:
        text = apply_tokens(text)
    if check_forbidden:
        for phrase in FORBIDDEN:
            if phrase in text:
                # apply_tokens scrubs forbidden phrases — if we still see
                # one here, something is wrong with the manifest.
                raise SystemExit(
                    f"forbidden phrase {phrase!r} still present after scrub in {src}"
                )
    dst.write_text(text, encoding="utf-8")


def copy_tree(rel_dir: str, *, transform: bool) -> None:
    src_root = SRC / rel_dir
    if not src_root.exists():
        return
    for path in sorted(src_root.rglob("*")):
        if path.is_dir():
            continue
        rel = str(path.relative_to(SRC))
        if is_excluded(rel):
            continue
        if path.suffix.lower() == ".pdf" and not keep_pdf(rel):
            continue
        dst = DEST / rel
        copy_file(path, dst, transform=transform, check_forbidden=transform)


def copy_entry(entry: str, *, transform: bool) -> None:
    """Copy one CORE/CONFIG entry, which may be a file or directory."""
    src = src_path(entry)
    rel = norm(entry)
    if not src.exists():
        # missing entries are non-fatal — manifest may list optional paths.
        return
    if src.is_dir() or is_dir_entry(entry):
        copy_tree(rel, transform=transform)
        return
    if is_excluded(rel):
        return
    if src.suffix.lower() == ".pdf" and not keep_pdf(rel):
        return
    copy_file(src, DEST / rel, transform=transform, check_forbidden=transform)


# 1) CORE — verbatim copy. We still run the token pass on CORE so that
#    stray references to the firm's name get scrubbed. The pass is a
#    no-op on files that don't contain any of the source values.
for entry in CORE:
    copy_entry(entry, transform=True)

# 2) CONFIG — token substitution, with forbidden-phrase guard.
for entry in CONFIG:
    copy_entry(entry, transform=True)

# 3) SEED — empty-shape stubs.
for entry in SEED:
    rel = norm(entry)
    target = DEST / rel
    target.mkdir(parents=True, exist_ok=True)
    keep = target / ".gitkeep"
    keep.write_text("", encoding="utf-8")

for stub_path, stub_body in SEED_STUBS.items():
    out = DEST / stub_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(stub_body, encoding="utf-8")

# 4) Strip any remaining FIRM paths that somehow made it through.
#    This runs BEFORE payload so payload files (e.g. README.md) can
#    overwrite a same-named FIRM file that we just removed.
for entry in EXCLUDE_FIRM:
    rel = norm(entry)
    target = DEST / rel
    if target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)

# 5) Payload — files sourced from `theseus-template/` in the source repo.
for entry in PAYLOAD:
    src = SRC / entry
    if not src.exists():
        continue
    rel_out = entry[len("theseus-template/"):] if entry.startswith("theseus-template/") else entry
    dst = DEST / rel_out
    copy_file(src, dst, transform=False, check_forbidden=False)
    # Preserve executable bit (bootstrap.sh in particular).
    if os.access(src, os.X_OK):
        dst.chmod(dst.stat().st_mode | 0o111)

# 6) Strip glob-based excludes from the output too.
for path in sorted(DEST.rglob("*")):
    if path.is_dir():
        continue
    rel = str(path.relative_to(DEST))
    if is_excluded_glob(rel):
        path.unlink(missing_ok=True)

# 7) Drop empty directories so the output is tidy.
for path in sorted(DEST.rglob("*"), reverse=True):
    if path.is_dir() and not any(path.iterdir()):
        try:
            path.rmdir()
        except OSError:
            pass

# 8) Final guard — no forbidden phrase survives anywhere in the output.
for path in sorted(DEST.rglob("*")):
    if not path.is_file():
        continue
    if is_binary(path):
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    for phrase in FORBIDDEN:
        if phrase in text:
            raise SystemExit(f"forbidden phrase {phrase!r} survived extraction in {path}")

print(f"[build_template] copied {sum(1 for _ in DEST.rglob('*') if _.is_file())} files into {DEST}")
PY

# git init + initial commit
if [[ "$DO_GIT" -eq 1 ]]; then
  AUTHOR_NAME="$(python3 - "$MANIFEST" <<'PY'
import sys, yaml
m = yaml.safe_load(open(sys.argv[1]))
print(m.get("output", {}).get("initial_commit_author_name", "Theseus Template Builder"))
PY
)"
  AUTHOR_EMAIL="$(python3 - "$MANIFEST" <<'PY'
import sys, yaml
m = yaml.safe_load(open(sys.argv[1]))
print(m.get("output", {}).get("initial_commit_author_email", "template@theseus.invalid"))
PY
)"
  COMMIT_MSG="$(python3 - "$MANIFEST" <<'PY'
import sys, yaml
m = yaml.safe_load(open(sys.argv[1]))
print(m.get("output", {}).get("initial_commit_message", "Initial commit"))
PY
)"

  (
    cd "$DEST"
    git init -q -b main
    git -c user.name="$AUTHOR_NAME" -c user.email="$AUTHOR_EMAIL" add -A
    git -c user.name="$AUTHOR_NAME" -c user.email="$AUTHOR_EMAIL" \
        commit -q -m "$COMMIT_MSG" --allow-empty
  )
  echo "[build_template] initialized git repo at $DEST with one commit"
else
  echo "[build_template] skipped git init (--no-git)"
fi

echo "[build_template] done."
