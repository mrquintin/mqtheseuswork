# Prompt Design Guide — Claude Code Batch Execution

This document describes the design conventions, structural patterns, and accumulated decisions behind the Claude Code prompt system used in the Theseus monorepo. Use it to replicate the approach in another project.

## Core architecture

The system has three layers:

1. **Prompt files** — numbered `.txt` files in `Claude_Code_Prompts/`, each a self-contained task for a single Claude Code agent session.
2. **Runner script** — `run_prompts.sh`, a bash script that feeds each prompt to `claude -p` sequentially, captures structured streaming output, and logs everything.
3. **Stream formatter** — `format_stream_events.py`, a Python script that parses Claude Code's `--output-format stream-json` NDJSON and prints a human-readable live summary to the terminal.

## Prompt design conventions

### Imperative agent-addressed style

Every prompt is written as a direct instruction to an implementation agent, not a description of desired state. This distinction matters: Claude interprets descriptive text as context rather than as a task.

Bad: "The system should have a PyInstaller spec file that bundles assets and excludes tensorflow."
Good: "Create `dialectic/dialectic.spec` — a PyInstaller spec file. Bundle the `assets/` directory as data. Exclude `tensorflow`, `tensorboard`, `jupyter`."

### Prompt anatomy

Each prompt follows this structure, in order:

```
# Claude Code Prompt N of M — Short title

**Sequence:** prompt N of M (Wave X). Report back when done.

**Before you start — read current state:**
1. Run `git status` and `git branch`.
2. Read [specific files] to understand existing structure.
3. Check if SCOPE files already exist. Do NOT overwrite correct work.

## Your task
[2-3 sentence summary of what the agent is doing and why]

## Prerequisites
[What must already be true for this prompt to work]

SCOPE (files you may create or modify — stay within this list)
- `path/to/file.py`      CREATE or MODIFY
- ...

## Step-by-step
1. [Explicit instruction with code snippets]
2. ...

## Verification
- [Concrete shell commands that confirm the work is correct]

## Prohibitions
- Do NOT [specific anti-pattern]
- ...
```

### Key design features

**Defensive-read preamble.** Every prompt starts by telling the agent to check `git status`, read the files it's about to touch, and inspect for partial work from prior runs. This makes prompts resumable — if a run fails partway, re-running the same prompt won't destroy completed work.

**SCOPE manifest.** Each prompt declares exactly which files it may create or modify. This serves two purposes: (a) the agent knows its boundary and won't edit unrelated files, (b) you can verify file-disjointness across prompts in the same wave.

**Step-by-step with code.** Instructions are numbered and include code snippets (Python, YAML, bash, etc.) showing the expected structure. The agent fills in implementation details, but the skeleton prevents misinterpretation of intent. Don't over-specify to the point where the agent can't make judgment calls, but don't under-specify to the point where it guesses your architecture.

**Verification section.** Concrete commands (pytest, type-checkers, syntax checks, import tests) that the agent runs before reporting back. These catch errors within the session rather than downstream.

**Prohibitions.** Explicit "DO NOT" rules for the most likely failure modes. Common prohibitions: don't modify files outside scope, don't add unnecessary dependencies, don't run expensive builds that belong to a later prompt, don't overwrite existing correct work.

### File-centric decomposition

Prompts are organized around **which files they touch**, not around narrative features. A single feature (e.g., "make Dialectic installable") spans multiple prompts — one for the packaging config, another for platform build scripts, another for CI/CD workflows. This is deliberate: it prevents file-overlap conflicts between prompts and keeps each prompt small enough for a single agent session.

### Wave structure

Prompts are grouped into waves. Within a wave, prompts touch disjoint file sets and can theoretically run in parallel (though the runner currently executes sequentially). Across waves, there are dependencies: Wave 2 prompts assume Wave 1 deliverables exist.

The wave structure is declared in the README and encoded in each prompt's header ("Wave 1 — independent" or "Wave 2 — depends on prompts 01, 03"). The runner executes in numeric order, which respects the wave ordering as long as you number Wave 1 prompts before Wave 2.

### Prompt sizing

Each prompt should be completable in a single Claude Code session — roughly 10–60 turns, producing 3–10 files. If a prompt requires more than ~15 files or involves complex algorithmic logic across many modules, split it. The round-3 experience showed that a single prompt trying to extend a 2,000-line models.py with 40+ new types hit the 60-turn cap at $21 — that was too large.

Rule of thumb: if explaining the task takes more than ~2 pages of text, or the FILES TOUCHED list exceeds 10 entries, consider splitting.

## Runner script design

### `run_prompts.sh`

The runner auto-discovers prompts by globbing `Claude_Code_Prompts/[0-9][0-9]_*.txt` and sorting numerically. Key features:

- **`claude -p "$(cat "$f")"`** — feeds the prompt text directly to Claude Code's headless/pipe mode.
- **`--output-format stream-json`** — Claude emits NDJSON events (tool calls, file reads/writes, assistant messages) that we capture.
- **`--model claude-opus-4-7`** — pins the model so all prompts use the same one. Change this to whatever model you want.
- **`--verbose`** — includes tool inputs/outputs in the stream.
- **Pipeline: `claude | tee raw.jsonl | python3 formatter.py | tee text.log`** — raw NDJSON is preserved for debugging, formatted output goes to the terminal and a text log.
- **`PIPESTATUS[0]`** — captures claude's exit code from the pipeline (not tee's).
- **`--from N` / `--only N`** — resume after failure or run a single prompt. Critical for iterative debugging.
- **`--continue`** — don't halt on failure (default is halt-on-first-failure).
- **`--skip-perms`** — passes `--dangerously-skip-permissions` to claude for fully unattended runs.
- **`--dry-run`** — shows the execution plan without running anything.
- **macOS bash 3.2 compatibility** — uses `while IFS= read -r` instead of `mapfile` (bash 4+), since macOS ships bash 3.2.

### `format_stream_events.py`

Reads NDJSON from stdin, extracts event types (read, write, edit, bash, tool_result, assistant message, etc.), and prints a colorized compact summary. This gives you live visibility into what the agent is doing without drowning in raw JSON.

### Log structure

All logs go to `.claude_code_runs/` with timestamps:
- `20260416-230000_01_dialectic_pyinstaller_config.raw.jsonl` — full NDJSON stream
- `20260416-230000_01_dialectic_pyinstaller_config.log` — formatted text output

### Archive pattern

When moving to a new round of prompts, the old prompts and their runner artifacts are moved into `Claude_Code_Prompts/archive_roundN/`. The runner script, `format_stream_events.py`, and the `.claude_code_runs/` logs are also copied there. This preserves the full history of what was executed.

## How to replicate in another project

1. Create a `Claude_Code_Prompts/` directory.
2. Write numbered `.txt` files following the prompt anatomy above. Start with a SCOPE manifest and work backward from which files need to change.
3. Group prompts into waves by checking file overlap: if two prompts both modify `src/config.ts`, they must be in different waves (and the earlier one comes first).
4. Copy `run_prompts.sh` and `format_stream_events.py` to the repo root.
5. Update the `--model` flag in `run_prompts.sh` to your preferred model.
6. Run `./run_prompts.sh --dry-run` to verify discovery, then `./run_prompts.sh` to execute.
7. If a prompt fails, inspect the `.claude_code_runs/` log, fix the prompt or the codebase, and resume with `./run_prompts.sh --from N`.

## Lessons learned

- **Descriptive prompts fail.** Claude reads "the system should have X" as information, not as a task. Write "Create X" or "Add X to file Y."
- **Large prompts fail.** A prompt that tries to do too much hits the turn cap or produces sloppy work in the later steps. Split aggressively by file.
- **Defensive preambles save re-runs.** Without them, re-running a prompt after partial success destroys the completed work.
- **Prohibitions prevent the most common drift.** Without explicit "DO NOT modify files outside scope," agents will helpfully refactor neighboring code.
- **The runner must capture the raw stream.** When something goes wrong at turn 45, you need the full NDJSON log to understand what happened. The formatted text log isn't enough.
- **Pin the model.** Different models produce different quality levels and have different context limits. Don't let it vary between prompts in a batch.
