# Round 18 — Consolidation, Empirical Execution, and Refined Excellence

Active batch authored 2026-05-08 immediately after Round 17 completed.
Round 17 added roughly 50 substantial features in parallel:
methodology operationalization, the QH benchmark, the calibration
loop, belief revision, source provenance, the adversarial swarm,
public surfaces, dialectic upgrades, observability, retention,
external critique, signing. The throughput was high; the entropy was
also high.

Round 18 has three jobs simultaneously:

1. **Stabilize** — schema audit, migration safety, API envelope
   unification, type alignment, module hierarchy, design system
   extraction, dead-code elimination, CI consolidation, naming
   convention enforcement, circular-dependency removal, config
   unification, observability completion (prompts 01–12).
2. **Run the experiments the prior round only built harnesses for**
   — QH benchmark, cross-model study, Householder ablation, red-team
   tournament, principle distillation, resolution backfill,
   self-critique, the first auto-paper (prompts 13–20).
3. **Refine the surfaces and depen the methodology** — methodology
   explorer v2, calibration scorecard v2, lineage v2, Currents
   dialectic quality, attention-queue signal, Explorer polish,
   provenance polish, print polish, public ask quality, mobile polish
   (prompts 21–30); aim-method-fit rubric, Bayesian belief layer,
   method retirement workflow, reviewer-agreement model, horizon
   calibration, cross-domain transfer study, severity rubric
   calibration (prompts 31–37).
4. **Document, validate, and open up** — single architecture document,
   RATIONALE drift repair, formal MQS spec, outside-reader onboarding,
   operations runbook, threat-model follow-up (38–43); critique pilot,
   replication outreach, first seasonal review, subscription cutover,
   methodology review week (44–48); accessibility review and final
   verification (49–50).

The active runnable batch is exactly the top-level numbered prompt
set 01–50.

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
./run_prompts.sh --from 13 --to 20    # the empirical-execution block
./run_prompts.sh --only 50
./run_prompts.sh --model claude-opus-4-7
./run_prompts.sh --continue
```

The runner uses the Claude Code CLI's existing login/subscription
path (`claude -p`), NOT an API key. Streaming via `--output-format
stream-json --include-partial-messages --verbose`, rendered through
`format_stream_claude.py` so tool calls and partial text appear live.
Raw JSONL persists at
`.claude_code_runs/<timestamp>_<prompt>.raw.jsonl`; the human-readable
log is at `.claude_code_runs/<timestamp>_<prompt>.log`.

`run_prompts.sh` discovers only top-level
`coding_prompts/[0-9][0-9]_*.txt` files. It does not descend into
`_paused/`, `archive_round*/`, or any other subdirectory.

## Audit

```bash
python3 coding_prompts/_audit_implementation.py
```

## Inter-prompt dependencies

The 50 prompts are arranged so that, in order, each only depends on
prompts before it. Selected dependencies worth knowing if you reorder:

- 01 (schema audit) blocks 02 (migration safety), 04 (type
  alignment), and 33 (method retirement).
- 03 (API envelope) is referenced by 21 (methodology explorer v2),
  22 (calibration scorecard v2), 29 (public ask quality), 47
  (subscriptions).
- 05 (module hierarchy) inserts shims; later prompts use the new
  paths but the shims remain through the round.
- 06 (design system) supplies primitives consumed by every v2
  prompt (21–30) and by 49 (a11y).
- 12 (observability completion) depends on Round 17 prompt 44.
- 13 (QH benchmark run) provides results consumed by 14 (cross-
  model), 15 (ablation), 21 (methodology explorer v2), 38
  (architecture doc), 41 (reader guide), 46 (seasonal review).
- 18 (resolution backfill) provides numbers for 22 (scorecard v2),
  35 (horizon calibration), 46 (seasonal review).
- 19 (self-critique pass) provides findings for 25 (attention queue
  signal) and 46 (seasonal review).
- 20 (first auto-paper) consumes 13, 18, 17 outputs.
- 31 (aim-method fit) modifies the MQS scorer; 40 (formal MQS spec)
  must follow.
- 37 (severity calibration) gates on having sufficient labeled
  objections from the live system; cold-start gating is in the
  prompt itself.
- 44 (critique pilot) and 45 (replication outreach) produce drafts
  for the founder to send; they do not auto-contact anyone.
- 50 must run last.

## Authoring philosophy

These prompts give direction, not code. They name the files to read,
the constraints to honor, the tests to write, and the SCOPE block
lists exact files to CREATE / MODIFY. The agent is expected to make
real engineering judgments on internal structure, error handling,
naming, and dependencies — not to recover code from the prompt.

The empirical-execution prompts (13–20) are the firm's first real
test of whether the Round 17 infrastructure does what it claims.
They produce real numbers. The agent is expected to publish honest
results, including unflattering ones; flattering-only publication
is a failure mode the prompts call out by name.

The pilot/outreach prompts (44–48) involve outside parties. The
agent never contacts them automatically; it produces drafts and
target lists for the founder to send.

## Archives

- `archive_round17_methodology_implementation/` — Round 17 (methodology
  operationalization, QH benchmark scaffolding, calibration loop,
  belief revision, source provenance, adversarial swarm, public
  surfaces, dialectic upgrades, observability, retention, external
  critique, signing — the 50-prompt round that built the substrate
  Round 18 stabilizes and exercises).
- `archive_round16_public_ux_implemented/` — Round 16 public-surface
  UX cleanup.
- Earlier archives back through round3.
