================================================================================
MARS ESTATE PROMPTS — How to use
================================================================================

Each numbered prompt is a self-contained instruction for a coding agent
(Claude Code, Cursor, Codex) working on the Mars_Estate_Dash repo.

USAGE
-----
1. Open the agent in the Mars_Estate_Dash repo so it has the codebase as
   context.
2. For each prompt, paste the FULL FILE CONTENTS into the agent.
3. After the agent reports done, verify the ACCEPTANCE CRITERIA at the
   bottom of the prompt.
4. Commit. Move to the next prompt.

Prompts are numbered in the order they should be executed.

GLOBAL CONVENTIONS THE PROMPTS ASSUME
-------------------------------------
- The repo at hand is Mars_Estate_Dash-main: Next.js 15 App Router,
  TypeScript, better-sqlite3 with sqlite-vec, Anthropic SDK + Voyage AI,
  chokidar Obsidian sync, local-only (no auth, no cloud deployment).
- The single SQLite file at data/mars.db is the database. Schema lives
  in lib/db.ts inside the migrate() function. New tables get appended
  there following the existing pattern (CREATE TABLE IF NOT EXISTS +
  PRAGMA table_info for idempotent ALTERs).
- Anthropic is the only LLM provider. Sonnet 4.6 (model id
  "claude-sonnet-4-6") for high-stakes judgment, Haiku 4.5 (model id
  "claude-haiku-4-5-20251001") for cheap classification.
- Voyage AI handles embeddings (voyage-3-large, 1024 dims). The
  existing lib/voyage.ts is the entry point.
- External data (email via Superhuman MCP, meetings via Granola MCP)
  flows through Cowork-scheduled tasks defined in scripts/. Long-period
  background work (weekly sweeps, monthly decay) should follow the
  same pattern (a new scripts/scheduled-task-*.md file).
- The repo's voice: Colin Yuan is non-technical, prefers black-box
  tools and one-command launches. Frame any operator-facing copy
  accordingly. The existing system prompt at lib/chat/prompt.ts is
  the reference for tone.

================================================================================
