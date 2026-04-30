#!/usr/bin/env python3
"""
Walk every archived prompt and decide whether it has been implemented.

A prompt is "implemented" when the files declared in its SCOPE block exist on
disk. We extract paths from lines like:

    - `path/to/file.py`                                                CREATE
    - `path/to/file.tsx`                                               MODIFY

and check each against the repo root.

Categories:
  IMPLEMENTED      all declared files exist
  PARTIAL          some exist, some don't (refactor or partial run)
  NOT_IMPLEMENTED  none exist
  UNCHECKABLE      no parseable SCOPE entries

Decision (matches the user's framing — "archive implemented, keep un-implemented"):
  IMPLEMENTED, PARTIAL                  → leave archived
  NOT_IMPLEMENTED                       → move back to top level
  UNCHECKABLE                           → leave archived (default to safe)

PARTIAL is intentionally NOT moved back. Older prompts whose targets were later
refactored show up as PARTIAL and shouldn't be re-run — they'd produce stale
files conflicting with the current architecture.
"""
from __future__ import annotations
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "Claude_Code_Prompts"
RUNS_DIR = REPO_ROOT / ".claude_code_runs"

# Lines that look like SCOPE entries:
#     - `some/path`                                                    CREATE
#     - `some/path`                                                    MODIFY (note)
#     - `some/path` CREATE
SCOPE_LINE_RE = re.compile(
    r"""^\s*-\s+`([^`]+)`\s+(?:CREATE|MODIFY)\b""",
    re.MULTILINE,
)

# Paths inside the prompt that are clearly NOT scope targets — exclude them
# even if they happen to match the regex via false positives.
PATH_BLACKLIST_PREFIXES = (
    "http://", "https://",
)


def extract_scope_paths(text: str) -> list[str]:
    paths = SCOPE_LINE_RE.findall(text)
    cleaned = []
    for p in paths:
        p = p.strip()
        if any(p.startswith(b) for b in PATH_BLACKLIST_PREFIXES):
            continue
        cleaned.append(p)
    return cleaned


def has_run_log(prompt_basename: str) -> bool:
    if not RUNS_DIR.is_dir():
        return False
    pattern = f"*_{prompt_basename}.raw.jsonl"
    return any(RUNS_DIR.glob(pattern))


def classify(paths: list[str]) -> tuple[str, int, int]:
    """Return (verdict, exists, total)."""
    if not paths:
        return ("UNCHECKABLE", 0, 0)
    exists = sum(1 for p in paths if (REPO_ROOT / p).exists())
    total = len(paths)
    if exists == total:
        return ("IMPLEMENTED", exists, total)
    if exists == 0:
        return ("NOT_IMPLEMENTED", exists, total)
    return ("PARTIAL", exists, total)


def main(argv: list[str]) -> int:
    apply = "--apply" in argv

    # Collect all .txt prompts under any archive folder.
    archives = sorted(
        [p for p in PROMPTS_DIR.glob("archive*") if p.is_dir()]
    )
    # Also recurse into subfolders for archive/Next_Round_Prompts/wave_*/.
    candidate_prompts: list[Path] = []
    for a in archives:
        candidate_prompts.extend(sorted(a.rglob("*.txt")))

    if not candidate_prompts:
        print("no archived prompts found")
        return 0

    rows: list[dict] = []
    for prompt_path in candidate_prompts:
        text = prompt_path.read_text(encoding="utf-8", errors="replace")
        paths = extract_scope_paths(text)
        verdict, exists, total = classify(paths)
        rows.append({
            "prompt": prompt_path,
            "rel": prompt_path.relative_to(PROMPTS_DIR),
            "verdict": verdict,
            "exists": exists,
            "total": total,
            "has_log": has_run_log(prompt_path.stem),
        })

    # Print report grouped by verdict for clarity.
    by_verdict: dict[str, list[dict]] = {
        "IMPLEMENTED": [], "PARTIAL": [],
        "NOT_IMPLEMENTED": [], "UNCHECKABLE": [],
    }
    for r in rows:
        by_verdict[r["verdict"]].append(r)

    for v in ("NOT_IMPLEMENTED", "PARTIAL", "UNCHECKABLE", "IMPLEMENTED"):
        if not by_verdict[v]:
            continue
        print(f"\n=== {v} ({len(by_verdict[v])}) ===")
        for r in by_verdict[v]:
            log_marker = "  log" if r["has_log"] else "no log"
            print(f"  {r['exists']:>3}/{r['total']:<3}  {log_marker}  {r['rel']}")

    # Action: move NOT_IMPLEMENTED prompts back to the top level.
    movers = by_verdict["NOT_IMPLEMENTED"]
    print(f"\n=== Action plan ===")
    print(f"  {len(by_verdict['IMPLEMENTED'])} IMPLEMENTED  → leave archived")
    print(f"  {len(by_verdict['PARTIAL'])} PARTIAL      → leave archived (likely refactored)")
    print(f"  {len(by_verdict['UNCHECKABLE'])} UNCHECKABLE  → leave archived (no SCOPE found)")
    print(f"  {len(movers)} NOT_IMPLEMENTED → move to top level of {PROMPTS_DIR.name}/")

    if not movers:
        print("\nNothing to move.")
        return 0

    if not apply:
        print("\n(dry run — pass --apply to actually move files)")
        return 0

    # Conflict check: don't overwrite anything at the top level.
    top_existing = {p.name for p in PROMPTS_DIR.glob("[0-9][0-9]_*.txt")}
    moved = 0
    for r in movers:
        src = r["prompt"]
        if src.name in top_existing:
            print(f"  SKIP (conflict at top level): {src.name}")
            continue
        dst = PROMPTS_DIR / src.name
        shutil.move(str(src), str(dst))
        moved += 1
        print(f"  moved: {r['rel']}  →  {src.name}")
    print(f"\nmoved {moved}/{len(movers)} prompts back to top level.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
