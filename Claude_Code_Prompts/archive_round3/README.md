# Claude Code Prompts — Sequential Round 3

Paste these into Claude Code one at a time, in order. Each prompt is self-contained, addresses Claude Code directly, and ends with a "report back when done" instruction so you know when it's safe to paste the next one.

## How to use

1. Open Claude Code at the repo root (`~/Desktop/Theseus`).
2. Open `01_models_py_extensions.txt`, copy its contents, paste into Claude Code.
3. Wait for Claude Code to report back: "Here are the files I created/modified and any notable choices."
4. Review the diff. If it looks good, paste the next prompt.
5. If something's off, ask Claude Code to fix it before proceeding.

## The 26 prompts

Each is numbered in execution order. The `Sequence` line at the top of each prompt tells you which prior prompts must be complete. Some groups of adjacent prompts touch disjoint files and CAN be run in parallel if you have multiple Claude Code sessions — each prompt notes this under "Parallelism (optional)".

| # | Prompt | Depends on |
|---|--------|-----------|
| 01 | models.py extensions | — |
| 02 | store.py + migration | 01 |
| 03 | methods/ registry + decorator | 01 |
| 04 | port coherence + geometry methods | 02, 03 |
| 05 | port extraction + synthesis methods | 02, 03 |
| 06 | CI lint + parity tests | 02, 03 |
| 07 | ledger/ package | 04–06 |
| 08 | cascade/ package | 04–06 |
| 09 | evaluation/ package | 04–06 |
| 10 | decay/ package | 04–06 |
| 11 | inference/ package | 07–10 |
| 12 | external_battery/ core | 07–10 |
| 13 | peer_review/ core | 07–10 |
| 14 | transfer/ package | 07–10 |
| 15 | rigor_gate/ core | 07–10 |
| 16 | external_battery adapters | 12 |
| 17 | peer_review roles | 13 |
| 18 | rigor_gate checks | 15 |
| 19 | docgen/ package | 14 |
| 20 | interop/ package | 14, 19, 18 |
| 21 | CLI main + foundation commands | 07–15 |
| 22 | CLI publication + gate commands | 14, 19, 20, 15 |
| 23 | founder portal pages | 11–20 |
| 24 | public site pages | 11–20 |
| 25 | shared API router | 11–20 |
| 26 | CI umbrella + cross-cutting checks | everything |

## Defensive-read preamble

Every prompt opens with a short instruction telling Claude Code to read the current state of the target files BEFORE writing, because an earlier automated orchestrator run partially modified `models.py` and left stale `round3/*` branches. The preamble tells Claude Code to:

1. Run `git status` / `git branch` and stop if it sees orchestrator leftovers.
2. For each file in scope, inspect what's already there and only add missing pieces.
3. Not overwrite existing correct work.
4. Not duplicate types / tests that already exist.
5. Ask you if it finds broken partial work, rather than silently continuing.

## Cleaning up from the prior orchestrator run

The orchestrator we tried before left artifacts. Run this once before prompt 1:

```bash
cd ~/Desktop/Theseus
rm -rf .orchestrator
# Remove any worktrees and branches the orchestrator created
git worktree list | grep -v "^$(pwd) " | awk '{print $1}' | xargs -I {} git worktree remove --force {} 2>/dev/null || true
git branch | grep "round3/" | xargs -n1 git branch -D 2>/dev/null || true
git status
```

If `git status` shows no modifications, your main branch is clean and you can start.

## Parallelism (optional)

If you run multiple Claude Code sessions, these groups can overlap:
- Prompts 02 + 03 (wave 2)
- Prompts 04 + 05 + 06 (wave 3)
- Prompts 07 + 08 + 09 + 10 (wave 4)
- Prompts 11 + 12 + 13 + 14 + 15 (wave 5)
- Prompts 16 + 17 + 18 + 19 (wave 6)
- Prompts 21 + 22 (wave 8)
- Prompts 23 + 24 + 25 (wave 9)

Each prompt's manifest is disjoint from its wave-mates, so parallel sessions shouldn't collide. Between waves, however, the next wave depends on the prior wave being finished — don't start wave N+1 prompts until wave N reports back.
