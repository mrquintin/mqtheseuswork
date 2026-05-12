# UI UX Round 19

This prompt batch is isolated from the active top-level Round 18 prompts.

Run from the repository root:

```bash
./coding_prompts/ui_ux_round19/run_prompts.sh
```

Useful filters:

```bash
./coding_prompts/ui_ux_round19/run_prompts.sh --dry-run
./coding_prompts/ui_ux_round19/run_prompts.sh --from 3
./coding_prompts/ui_ux_round19/run_prompts.sh --to 5
./coding_prompts/ui_ux_round19/run_prompts.sh --only 10
./coding_prompts/ui_ux_round19/run_prompts.sh --continue
```

The runner uses the installed Claude Code CLI subscription login via `claude -p`.
It does not use an Anthropic API key and explicitly removes Anthropic API-key
environment variables before each prompt.

Prompt order:

1. UI audit and design contract.
2. Global typography, navigation, and buttons.
3. Conclusion detail declutter.
4. Knowledge and conclusion list refinement.
5. Audio transcript/source explorer cleanup.
6. Upload and Ask workflow clarity.
7. Ops and founder Currents surfaces.
8. Public home, Currents, and articles empty states.
9. Button interactivity and performance hardening.
10. Visual verification and report.

