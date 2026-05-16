# `_META_PROMPT.md` — the reusable round-design meta-prompt

Paste the content below (between the BEGIN and END markers) into a new
chat, then **attach the meeting transcript / voice-memo transcript / written
brief** as a file. Claude will then archive the prior round, author the
feature prompts, author the bug-testing companion prompts, update the
README, and verify the runner picks everything up — all in one pass, in
the established Theseus convention.

Underscore prefix on the filename is intentional: `run_prompts.sh`'s
top-level glob (`[0-9][0-9]_*.txt`) ignores this file.

---

```
======================== BEGIN META-PROMPT ========================

ROLE & CONTEXT
You are extending the Theseus repo at /Users/michaelquintin/Desktop/Theseus.
This is the prompt-driven build cadence Michael (the founder) uses to
extend the platform: each round translates a meeting / voice memo / brief
into a numbered set of executable prompts that the Claude Code CLI runs
sequentially via run_prompts.sh.

INPUT
A meeting transcript, voice memo transcript, or written brief is attached
to this message. It contains a mix of:
  - explicit feature requests
  - vague directional ideas that need to be fleshed out into specific code
    changes
  - bug reports
  - strategic / identity / positioning changes
  - decisions about what NOT to do
Parse all of it. Flesh out the vague items by extrapolating concrete
implementation work consistent with the firm's existing architecture and
prior rounds.

STANDING CONVENTIONS (always honor these)

Voice & style for prompts:
  - Bare `SCOPE` block at the end of each prompt (not `## SCOPE`) listing
    backtick-quoted file paths with CREATE / MODIFY / CREATE-OR-MODIFY /
    DELETE / MODIFY-OR-DELETE suffixes. The audit script parses these.
  - Each prompt opens with "You are operating in
    /Users/michaelquintin/Desktop/Theseus."
  - "Goal:" paragraph, then concrete worked examples where the concept is
    new, then "Before you start — read:" with 3-5 numbered files,
    "Implement:" with lettered subsections (A, B, C...), "Constraints"
    section, "SCOPE" block. Match the style of recent archived rounds
    (look at archive_round18_completed/ for canonical examples).
  - Length per prompt: ~100-200 lines. Dense, terse, specific.

Safety properties that must NEVER weaken in any round:
  - Eight-gate safety contract on every live-money path
    (noosphere/noosphere/forecasts/safety.py)
  - Verbatim-citation discipline on every LLM output that cites sources
  - No-autonomous-live-trading: every live order requires per-bet operator
    confirmation
  - Provenance demarcation (PROPRIETARY / ENDORSED_EXTERNAL / etc.) is
    upload-time, never inferred
  - Secrets never leave the operator's machine; .env.live workflow only;
    .gitignore blocks .env.live*

Architectural conventions:
  - Three components: theseus-codex/ (Next.js frontend), dialectic/, and
    noosphere/ (Python backend). All migrations are additive (Prisma +
    Alembic both, in parity).
  - "Theseus codex" the product is the Next.js app. "OpenAI Codex CLI"
    is NOT used; the runner uses Claude Code CLI (`claude -p`).
  - pdflatex for any PDF deliverable (founder preference). Two-pass
    compilation; commit the PDF + .tex.
  - Logs are structured JSON, one event per line, never print().
  - Operator-only routes go under (authed)/ in Next.js routing AND under
    /v1/operator/ in FastAPI with HMAC-protected signatures.

DELIVERABLES PER ROUND (all required)

1. Archive prior round. The current top-level coding_prompts/[0-9][0-9]_*.txt
   prompts are completed; move them into
   coding_prompts/archive_round<N>_completed/ (figure out N by inspecting
   what archives already exist; the next round number is N+1 of the
   highest existing). Also move the round's README + any FORECASTS_DESIGN
   / RELEASE_CHECKLIST / round-specific docs in the top level of
   coding_prompts/.

2. Author feature prompts (the bulk of the round).
   - Translate every directive from the transcript into a prompt.
   - For vague directives: flesh them out by extrapolating concrete code
     work consistent with the existing architecture.
   - Number them 01_<slug>.txt through NN_<slug>.txt at the top level of
     coding_prompts/.
   - Each has the standard structure above with a SCOPE block.

3. Author bug-testing companion prompts (REQUIRED, not optional — this
   was made permanent in Round 19b).
   These come AFTER the feature prompts in numbering. Always include
   coverage for, at minimum:
     - migration linearity + Prisma↔SQLModel parity (catches the
       single largest cross-round break category)
     - import-cycle enforcement + API↔TypeScript type contract
     - end-to-end smoke harness (every public route, CLI --help,
       scheduler tick)
     - integration test for any new multi-module pipeline the round adds
     - env-var validation + boot-time refusal for new required vars
     - sandbox / safety regression for any new EVAL / LLM / external
       API surface
     - bug-replay catalog update for any new bug class observed
     - CI workflow + tooling + doc freshness check
     - pre-sync gate update (the ready-to-sync.sh script gets the new
       round's checks added to its sequence)
     - final meta-verification (the round's own "did all the
       bug-testing infrastructure work?" pass)
   Scale this list to the round — a small round may not need every item,
   but you must justify any omission in the round README.

4. README at coding_prompts/README.md describing the round, its waves,
   and a daily-driver invocation section.

5. Verify the runner picks up only the new prompts via a dry-run.
   run_prompts.sh's glob is [0-9][0-9]_*.txt at the top level of
   coding_prompts/. Archives are subdirectories; they're ignored.
   The runner already auto-runs the ready-to-sync gate after a clean
   batch (Round 19b prompt 27 + the run_prompts.sh integration after).

WORKING SEQUENCE

Step 1: Read the attached transcript end-to-end. Don't skim.

Step 2: Output a brief analysis of what you extracted from the transcript:
   - Explicit directives, listed.
   - Vague ideas, listed with your proposed fleshing-out.
   - Anything you're uncertain about — list as open questions for the
     founder to answer before you proceed. STOP and wait for answers if
     any open question would materially change the round.

Step 3: Once cleared, archive the prior round.

Step 4: Author the feature prompts in numerical order. Each as its own
   file. Don't batch into one — every prompt is independently runnable
   by run_prompts.sh.

Step 5: Author the bug-testing companion prompts. Number them
   continuously after the features. Include the gate-update prompt
   (the ready-to-sync.sh's sequence gains the new round's checks).

Step 6: Write the round's README.

Step 7: Dry-run the runner to confirm the new prompt set is picked up
   in order with the right count.

Step 8: Report back to the founder:
   - Round number, total prompt count, feature/bug-testing split.
   - Where the canonical worked examples are in the feature prompts
     (the "arms-race algorithm" pattern of the founder being able to
     point at and understand a concrete shipping artifact).
   - What's intentionally NOT in this round (the "this is for the next
     round" list).

USER PREFERENCES (these override defaults)

  - Rigor over warmth. No "great question!" preambles. No hedging that
    isn't grounded in a specific uncertainty.
  - When the founder writes "make me a guide / report / explainer /
    document of some kind," output a pdflatex-built PDF unless they
    specify otherwise.
  - When the founder reports a bug, ALWAYS:
      (a) acknowledge it as a real failure mode if it is one,
      (b) add it to the bug-replay catalog (the most recent round's
          equivalent of coding_prompts/archive_round*/25_bug_replay_*.txt
          or its successor in the current round),
      (c) ensure a regression test exists guarding against recurrence.

ASK BEFORE AUTHORING IF

  - The round implies a new data layer (new top-level entity, new
    migration class). Confirm naming + shape with the founder.
  - The round implies a new financial-exposure surface (new bet kind,
    new exchange adapter). Confirm the eight-gate inheritance + the
    operator confirmation path.
  - The round implies a new LLM call pathway. Confirm the budget guard
    + the abstention conditions.
  - The transcript contradicts a prior architectural decision. Flag
    explicitly with the contradicting source + the prior decision +
    your proposed resolution.

BEGIN

Read the attached transcript / brief now. Report your Step 2 analysis,
then proceed unless you have a blocking open question.

========================= END META-PROMPT =========================
```

## How to use this

1. Save the block above (between BEGIN and END markers) as your reusable
   prompt. You can keep it in a notes app, a snippet manager, or pull it
   from this repo at `coding_prompts/_META_PROMPT.md`.

2. Open a new chat with Claude. Paste the BEGIN/END block. Attach the
   meeting transcript or voice-memo transcript as a file.

3. Claude reports its Step 2 analysis. Either confirm or answer the
   open questions, then it proceeds through the round.

4. After the round is authored, run it locally:
   ```bash
   cd ~/Desktop/Theseus
   ./run_prompts.sh
   ```
   The auto-gate (Round 19b prompt 27 + the run_prompts.sh integration)
   runs after the prompts complete. If the gate fails, the runner
   surfaces the structured report and blocks sync.

## Maintenance notes

This meta-prompt is itself living. Whenever a new convention lands
(e.g., a new standing safety property, a new CLI flag, a renamed
component), update the appropriate section. The current version
reflects state as of the round following Round 19b.

Sections most likely to drift:
  - "Architectural conventions" — when components are added, renamed,
    or restructured.
  - "Bug-testing companion prompts" minimum coverage — as the firm
    accumulates new bug classes, the standing minimum coverage list
    grows.
  - "Ask before authoring if" — gates for things the agent should
    never decide unilaterally.

Bump the document when you bump those.
