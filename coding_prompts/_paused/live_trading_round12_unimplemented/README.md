# Paused Round 12 Live-Trading Prompts

These prompts were not archived as implemented.

They were moved out of the active top-level batch because their own `SCOPE` blocks still had missing deliverables during the quick check. Keeping them top-level would cause the current `run_prompts.sh` batch to enter an unrelated credential-gated live-trading wave.

Resume this group only when the intended task is live-trading activation and the operator has populated the required live/demo environment files.

Classification evidence:

| Prompt | Why paused instead of archived |
|---|---|
| 18 credential validator | Missing `noosphere/scripts/validate_live_credentials.py`, `noosphere/scripts/__init__.py`, and `noosphere/tests/test_validate_live_credentials.py`; only the shared CLI file and Round 10 checklist are present. |
| 19 production database migration | Missing all declared migration deliverables: `scripts/migrate_production.sh`, `scripts/migrate_production_dry_run.sh`, `docs/operator/PRODUCTION_MIGRATION.md`, and `noosphere/tests/test_migrate_production_script.py`. |
| 20 demo/testnet integration | Missing `noosphere/tests/test_live_demo_integration.py`, `noosphere/pytest.ini`, `scripts/run_demo_integration.sh`, and `docs/operator/DEMO_INTEGRATION.md`; only the existing noosphere test conftest is present. |
| 21 operator rehearsal | Missing `coding_prompts/OPERATOR_REHEARSAL.md`, `coding_prompts/LIVE_BET_LOG.md`, and `noosphere/scripts/rehearsal_status.py`; the shared CLI file exists but the rehearsal package does not. |
| 22 deployment/observability | Missing `theseus-codex/vercel.json`, production compose/systemd files, alert/dashboard files, operator deploy docs, and alert tests; `current_events_api/current_events_api/metrics.py` exists but the deployment wave is not implemented. |

Do not move these back to the top-level runnable batch as "done". Either resume
them intentionally as live-trading activation work, or reclassify them only after
their scope files exist and their safety checks have been run.
