# UI UX Round 20

Created: 2026-05-11

This is an isolated Claude Code prompt batch for a broad Theseus Codex
interface cleanup plus a founder-alpha push toward algorithmized
market decision making. The later prompts extend that decision system
so empirical case studies and abstract contradiction-testable
principles both feed logic-based market and institutional decisions. It
is intentionally not included in the top-level Round 18 runner because
the active top-level `coding_prompts/01_*.txt` through `50_*.txt`
prompts are still partial or unimplemented by the audit script.

The batch is based on a live path walk of:

- `https://www.theseuscodex.com/`
- `/currents`
- `/dashboard`
- `/knowledge`
- `/knowledge?tab=transcripts`
- `/conclusions/c_2276f14a65124a1898843fb3`
- `/transcripts/c6080d00458676eb57380e57d`
- `/upload`
- `/ask`
- `/founder-currents`
- `/ops`

## Run

```bash
cd /Users/michaelquintin/Desktop/Theseus
./coding_prompts/ui_ux_round20/run_prompts.sh
```

Useful filters:

```bash
./coding_prompts/ui_ux_round20/run_prompts.sh --dry-run
./coding_prompts/ui_ux_round20/run_prompts.sh --from 3
./coding_prompts/ui_ux_round20/run_prompts.sh --to 6
./coding_prompts/ui_ux_round20/run_prompts.sh --only 12
./coding_prompts/ui_ux_round20/run_prompts.sh --continue
./coding_prompts/ui_ux_round20/run_prompts.sh --model claude-opus-4-7
```

The runner uses the Claude Code CLI subscription/login path
(`claude -p`). It deliberately unsets Anthropic/Claude API-key
environment variables before each prompt so it does not run through an
API key.

Logs are written to `.claude_code_runs/ui_ux_round20/`.

## Prompt Order

1. Audit contract and design principles.
2. Global typography, language, shell, and buttons.
3. Dashboard and attention queue.
4. Conclusion detail declutter.
5. Knowledge, lists, and explorer surfaces.
6. Audio transcript reading experience.
7. Upload and processing feedback.
8. Ask and route consistency.
9. Currents and public publication surfaces.
10. Ops automation and script visibility.
11. Performance, interactivity, and navigation reliability.
12. UI visual verification and report.
13. Noosphere algorithmized decision architecture.
14. Logic-market metric engine.
15. Market monitoring scheduler and scripts.
16. Founder-alpha portfolio setup and credentials.
17. Live execution safety and order lifecycle.
18. Algorithmic portfolio UI and decision traces.
19. Market-system verification and founder-alpha runbook.
20. Empirical case-study extraction and schema.
21. Abstract principle abstraction and transfer graph.
22. Analogical transfer and future case monitoring.
23. Multi-perspective game-theoretic decision engine.
24. Case/principle/decision UI surfaces.
25. Empirical/abstract decision verification.

Run in order unless a previous prompt already completed cleanly and the
later prompt explicitly says it can stand alone.

Prompts 13-19 deliberately keep live capital deployment behind
credential checks, explicit live enablement, bankroll/risk limits,
authorization, per-bet confirmation, and kill-switch health. The goal is
for monitoring, metric application, paper trading, and candidate
generation to start once setup is complete, while live orders remain
bounded by auditable safety gates.

Prompts 20-25 extend the market engine beyond direct probability/price
comparison. They require Noosphere to extract empirical cases from
sources, abstract contradiction-testable principles, monitor future
cases against those principles, reject superficial analogies, and run
decisions through multiple explicit frames such as incentives,
coordination, principal-agent dynamics, reflexivity, option value,
contradiction pressure, and empirical transfer.
