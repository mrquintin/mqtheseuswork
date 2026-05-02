# Round 13 Conversation Geometry Archive

Archived 2026-05-02.

These prompts were removed from the active top-level prompt batch only after an
implementation audit. The audit standard was deliberately narrow and checkable:
each prompt's declared SCOPE paths had to exist in the repository, and the
conversation-geometry regression tests had to run from `theseus-codex/`.

Audit evidence:

| Prompt | SCOPE result | Landed evidence |
| --- | ---: | --- |
| `01_conversation_geometry_metrics_contract.txt` | 2/2 | `theseus-codex/src/lib/conversationGeometry.ts` and `theseus-codex/src/__tests__/conversationGeometry.test.ts` exist. |
| `02_transcript_harvest_table_ui.txt` | 5/5 | Transcript page wiring, `ConversationGeometryPanel.tsx`, supporting styles, and tests exist. |
| `03_point_causality_and_catalyst_explanations.txt` | 4/4 | Catalyst labels, anchors, UI rendering, and regression coverage exist. |
| `04_year_end_podcast_statistics.txt` | 4/4 | Closed-year statistics logic, transcript page rendering, styles, and tests exist. |
| `05_public_accessibility_and_readability_pass.txt` | 2/2 | Conversation geometry UI and global style targets exist. |
| `06_prompt_archive_and_runner_hygiene.txt` | 4/4 | Round 12 implemented archive, paused live-trading archive, prompt README, and root runner exist. |
| `07_visual_verification_and_regression_checks.txt` | 3/3 | Conversation geometry tests, transcript page tests, and transcript e2e spec exist. |
| `08_followup_identity_and_llm_analysis_hooks.txt` | 1/1 | Prompt README update exists. |

The archive claim is not "every possible product edge case is perfect." It is:
the prompt batch has landed enough code and regression coverage that rerunning
the same top-level prompts would duplicate work rather than create a fresh
active batch. Future repairs should target the implementation directly, not move
these prompts back to `coding_prompts/`.

Verification commands:

```bash
python3 coding_prompts/_audit_implementation.py
cd theseus-codex && npm run test -- conversationGeometry transcriptPage
```
