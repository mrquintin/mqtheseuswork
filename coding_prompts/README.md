# Methodological Reorientation Prompt Batch

Active batch created 2026-05-02 from the transcript requesting that Noosphere
capture "how we come to conclusions," not only "what we conclude."

The active runnable batch is exactly the top-level numbered prompt set:

1. `01_noosphere_methodology_contract.txt`
2. `02_codex_methodology_persistence.txt`
3. `03_methodology_reanalysis_backfill.txt`
4. `04_publication_methodology_review.txt`
5. `05_public_methodology_surfaces.txt`
6. `06_transcript_methodology_explorer.txt`
7. `07_verification_and_regression.txt`
8. `08_prompt_archive_runner_hygiene.txt`

`run_prompts.sh` discovers only top-level `coding_prompts/[0-9][0-9]_*.txt`
files. It does not descend into `_paused/`, `archive_round*/`, or any other
subdirectory.

## Run

```bash
cd /Users/michaelquintin/Desktop/Theseus
./run_prompts.sh
```

Useful filters:

```bash
./run_prompts.sh --dry-run
./run_prompts.sh --from 4
./run_prompts.sh --to 6
./run_prompts.sh --from 2 --to 6
./run_prompts.sh --only 06
./run_prompts.sh --model gpt-5.3-codex
./run_prompts.sh --continue
```

The runner uses the OpenAI Codex CLI login/subscription path (`codex exec`), not
an OpenAI API key. It also clears common OpenAI API-key environment variables
before each Codex invocation so Cursor shells with stale API-key variables still
use the Codex CLI login path. Every Codex session is streamed to the terminal
and captured in `.codex_runs/<timestamp>_<prompt>.log`; long calls keep the
existing 30-second heartbeat/progress output.

Each prompt tells Codex to inspect current code and tests first, verify already
landed work, and make only necessary repair edits. Reruns should therefore be
idempotent.

## Archives

The previously active conversation-geometry batch is archived under
`archive_round13_conversation_geometry_implemented/`. Its README records the
scope audit used to justify archiving it as implemented work.

The active audit command is:

```bash
python3 coding_prompts/_audit_implementation.py
```

Paused or historical prompts remain in subdirectories for reference, but the
root runner intentionally ignores them.
