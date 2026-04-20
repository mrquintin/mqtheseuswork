# Next-Round Technical Prompts — Wave-Organized, File-Partitioned

This directory is organized so that each prompt owns a disjoint file set and can be assigned to an independent agent. The waves represent hard sequencing: every prompt in `wave_N/` depends only on `wave_1/ ... wave_{N-1}/` having completed. Inside a wave, prompts do not touch each other's files and may run in parallel.

## The ten waves

| Wave | Purpose | # prompts | Parallelism |
|------|---------|-----------|-------------|
| 1 | Bedrock types — `models.py`                                                | 1  | serial    |
| 2 | Scaffolding — `store.py` + migrations, method registry + decorator         | 2  | full      |
| 3 | Port existing judgment functions into `methods/`; CI lint; candidate extractor | 3  | full      |
| 4 | Core self-contained subsystem packages (no inter-deps)                     | 4  | full      |
| 5 | Derived subsystem packages (each depends on one or more Wave-4 packages)   | 5  | full      |
| 6 | Package completions — adapters, reviewer roles, gate checks, docgen        | 4  | full      |
| 7 | Methodology Interoperability Package                                       | 1  | serial    |
| 8 | CLI commands (grouped by non-overlapping files)                            | 2  | full      |
| 9 | Founder portal pages, public site pages, API routers                       | 3  | full      |
| 10 | CI invariants umbrella                                                    | 1  | serial    |

Total: 26 prompts.

## Why waves

The previous 7-file layout still had implicit ordering inside each file; an agent reading a file had to serialize the work. Waves externalize that ordering, so:

- A team of 4–5 agents can drain a wave in parallel.
- An orchestrator only needs to know "wave N-1 green → kick off wave N" — no prompt-level dependency tracking.
- When a wave has fewer prompts than available agents, the unused agents can prepare for the next wave (read prerequisites, draft tests).

## File-ownership invariant

Each prompt has an exhaustive `FILES TOUCHED` manifest at the top. **No two prompts — regardless of wave — should share a file in that manifest.** The single exception is a rare `MODIFY` on a pre-existing codebase file, which is always owned by exactly one prompt (called out in the manifest with `MODIFY (sole round-3 owner)`).

If an agent finds it needs to edit a file outside its manifest, the correct response is to stop and flag — do not edit. The manifest is the contract.

## Shared invariants (prepend to every Cursor session)

> You are working inside the Theseus monorepo. The product direction, recorded in `docs/Methodological_Reorientation.pdf` and `THE_META_METHOD.md`, is that Theseus is a firm whose product is truth-finding methodology, not truth claims. Obey the invariants established in earlier rounds: every module boundary is type-validated with pydantic (Python) or TypeScript types (TS); `unresolved` is a first-class output of any judgment function; no component phones home; every new module comes with pytest or vitest tests; every conclusion is traceable to the artifacts it was derived from. In addition, honor these round-three invariants: (a) every new judgment function is a registered method with a versioned MethodSpec and produces an audit-ledger entry per call; (b) nothing that ships to the public layer bypasses the rigor gate; (c) every new external-facing artifact is signed with the corpus hash at publication; (d) your prompt's FILES TOUCHED manifest is its contract — if you need to edit a file outside it, stop and ask.

## Cross-wave dependency graph (summary)

```
wave_1 (models)
   └─> wave_2 (store, registry)
          └─> wave_3 (ports, ci lint)
                 └─> wave_4 (ledger, cascade, evaluation, decay)
                        ├─> wave_5 (inference, ext_battery_core, peer_review_core, transfer, rigor_gate_core)
                        │      └─> wave_6 (adapters, reviewer roles, gate checks, docgen)
                        │             └─> wave_7 (interop)
                        │                    └─> wave_8 (cli)
                        │                           └─> wave_9 (ui, api)
                        │                                  └─> wave_10 (ci umbrella)
```

Decay (wave_4) and rigor_gate (wave_5) carry stub checks for upstream features that land later in wave_6; stubs auto-pass and are upgraded as their upstream lands. This decoupling is load-bearing — it is what lets gate and decay ship in their own wave.
