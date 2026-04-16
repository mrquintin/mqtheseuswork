# Follow-ups after Phase 7 dry run

- **Graph / ingest bridge** — Dialectic JSONL ingest populates SQLite but does not automatically sync claims into `graph.json`; operators still need a promotion path or export step so principles and `CONTRADICTS` edges exist before synthesis.
- **Restore safety** — Consider interactive confirmation instead of only `--force` when overwriting a populated `THESEUS_DATA_DIR`.
- **Session research vs Store** — `session_research` writes JSON under `synthesis/research_sessions/`; optional persistence into `research_suggestion` rows is not wired from that command.
- **Log correlation** — File sink duplicates stdout JSON; add a shared `correlation_id` in both places if operators need to stitch multi-process runs.
- **Real-session dry run** — Run the documented cycle against a full-length exported session on a laptop, record wall times, and tighten `THESEUS_SYNTHESIS_MAX_WORKERS` guidance per hardware class.
