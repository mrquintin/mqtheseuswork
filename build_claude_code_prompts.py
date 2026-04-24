#!/usr/bin/env python3
"""Transform Next_Round_Prompts/wave_*/*.txt into Claude_Code_Prompts/NN_*.txt
with a flat numbering suitable for sequential paste into Claude Code.

Changes applied:
  * Flattens wave hierarchy into a single 01..26 sequence.
  * Strips box-decoration dividers (rows of ═ / ─ / - / =).
  * Removes orchestrator-specific language ("sibling agent in wave X").
  * Adds a defensive-read preamble so each prompt inspects existing state before
    writing — critical because a prior orchestrator run may have left partial
    changes in the repo.
  * Adds a closing "report back" instruction.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC  = ROOT / "Next_Round_Prompts"
DST  = ROOT / "Claude_Code_Prompts"


def parse_title(body: str) -> str:
    first = body.split("\n", 1)[0]
    m = re.match(r"WAVE \d+ / PROMPT \d+ — (.+?)\s*$", first)
    return m.group(1) if m else "Untitled"


def strip_dividers(line: str) -> bool:
    """Return True if this line is a pure decoration divider and should be dropped."""
    return bool(re.match(r"^[═─=\-]{10,}\s*$", line))


def scrub_sibling_language(line: str) -> str:
    patterns = [
        (r"\b(Three|Four|Two|A|One) sibling agents? in wave \d+ (are|is) (working on|on)[^.]+\.", ""),
        (r"\bThe sibling agent in wave \d+ will[^.]+\.", ""),
        (r"\bA sibling agent in wave \d+ is[^.]+\.", ""),
        (r"\b(sibling agent'?s?\s+)", ""),
        (r"\bStay inside (your|the) FILES TOUCHED manifest\.\s*", ""),
        (r"\bStay inside (your|the) manifest\.\s*", ""),
        # "do NOT touch their files" → "do NOT edit files outside the manifest"
        (r"do NOT touch their files\.", "do NOT edit files outside the scope listed here."),
        (r"Do not touch their files\.", "Do not edit files outside the scope listed here."),
    ]
    out = line
    for pat, repl in patterns:
        out = re.sub(pat, repl, out)
    return out


def defensive_preamble(seq: int, total: int, title: str, parallel_ids: list[int]) -> str:
    """Return the new opening block that replaces the original WAVE X / PROMPT Y header."""
    seq_note = (
        f"**Sequence:** prompt {seq} of {total}. Complete prompts 1..{seq-1} before starting this one. "
        f"When you finish, report back with: files you created/modified, any notable choices, any blockers. "
        f"I'll then paste the next prompt."
    )
    parallel_note = ""
    if len(parallel_ids) > 1:
        peers = [p for p in parallel_ids if p != seq]
        parallel_note = (
            f"\n\n**Parallelism (optional):** prompts {', '.join(str(p) for p in parallel_ids)} "
            f"touch disjoint files and could run in parallel Claude Code sessions if you want."
        )
    defensive = (
        "\n\n**Before you start — read current state:**\n"
        "1. Run `git status` and `git branch` to see the current branch state.\n"
        "2. If you see stray branches matching `round3/*` or a `.orchestrator/` directory from a prior automated run, tell me and stop; we'll clean them up before continuing.\n"
        "3. For every file listed under SCOPE below, check whether it already exists and what it contains. "
        "If parts of the work described here are already done (from a previous attempt), "
        "INSPECT what is there and only add the missing pieces. Do NOT overwrite existing, correct work. "
        "Do NOT duplicate types or tests that already exist.\n"
        "4. If you find partial work that is clearly broken or half-finished, ask me whether to complete it or discard and restart that piece."
    )
    return (
        f"# Claude Code Prompt {seq} of {total} — {title}\n\n"
        f"{seq_note}{parallel_note}{defensive}\n"
    )


def transform(body: str, seq: int, total: int, parallel_ids: list[int]) -> str:
    title = parse_title(body)
    lines = body.split("\n")
    # Drop first line (original WAVE header); everything else processed.
    out_lines: list[str] = []
    for line in lines[1:]:
        if strip_dividers(line):
            continue
        out_lines.append(scrub_sibling_language(line))

    # Rename section label FILES TOUCHED → SCOPE (more natural for Claude Code users)
    body2 = "\n".join(out_lines)
    body2 = re.sub(r"^FILES TOUCHED[^\n]*$", "SCOPE (files you may create or modify — stay within this list)", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^YOUR TASK\s*$", "## Your task", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^PREREQUISITES[^\n]*$", "## Prerequisites", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^STEP-BY-STEP[^\n]*$", "## Step-by-step", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^STEPS\s*$", "## Steps", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^TESTS(?:[^\n]*)?$", "## Tests", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^HOW TO VERIFY YOU ARE DONE\s*$", "## How to verify", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^DO NOT\s*$", "## Do not", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^OUT OF SCOPE\s*$", "## Out of scope", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^PITFALLS\s*$", "## Pitfalls", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^COMMAND SURFACES?\s*$", "## Command surfaces", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^SPEC FIELDS[^\n]*$", "## Spec fields", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^TYPES TO ADD\s*$", "## Types to add", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^MODIFY EXISTING MODELS\s*$", "## Modify existing models", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^TABLES TO CREATE\s*$", "## Tables to create", body2, flags=re.MULTILINE)
    body2 = re.sub(r"^STORE METHODS TO ADD\s*$", "## Store methods to add", body2, flags=re.MULTILINE)

    # Collapse runs of blank lines
    body2 = re.sub(r"\n{3,}", "\n\n", body2)

    head = defensive_preamble(seq, total, title, parallel_ids)
    tail = (
        "\n\n---\n\n"
        "**When you're finished:** report back with (a) files you created/modified, "
        "(b) any non-obvious choices you made, (c) any blockers. "
        "I'll paste the next prompt after I've reviewed your summary.\n"
    )
    return head + body2.strip() + tail


def main():
    DST.mkdir(parents=True, exist_ok=True)

    # Collect all prompts in wave order
    wave_dirs = sorted(
        [d for d in SRC.iterdir() if d.is_dir() and d.name.startswith("wave_")],
        key=lambda d: int(re.match(r"wave_(\d+)", d.name).group(1)),
    )
    all_files: list[tuple[int, Path]] = []
    for wd in wave_dirs:
        wave_num = int(re.match(r"wave_(\d+)", wd.name).group(1))
        for f in sorted(wd.glob("*.txt")):
            all_files.append((wave_num, f))

    total = len(all_files)

    # Group by wave for parallelism annotations
    wave_members: dict[int, list[int]] = {}
    for i, (wave_num, _) in enumerate(all_files, 1):
        wave_members.setdefault(wave_num, []).append(i)

    for seq, (wave_num, src_path) in enumerate(all_files, 1):
        body = src_path.read_text(encoding="utf-8")
        parallel_ids = wave_members[wave_num]
        new_body = transform(body, seq, total, parallel_ids)
        slug = re.sub(r"^\d+_", "", src_path.stem)
        dst_path = DST / f"{seq:02d}_{slug}.txt"
        dst_path.write_text(new_body, encoding="utf-8")

    print(f"Wrote {total} prompts to {DST}/")


if __name__ == "__main__":
    main()
