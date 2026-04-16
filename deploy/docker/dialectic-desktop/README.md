# Dialectic desktop packaging (SP06)

The `dialectic/` package is a **Python** desktop tool (PyQt6 UI in `dialectic/dashboard.py`), not an Electron app.

**Options (investigate per release):**

1. **PyInstaller / Briefcase** — bundle Python + Qt for macOS / Windows / Linux (closest to “one binary”).
2. **Tauri + sidecar** — thin native shell invoking the existing Python CLI (`python -m dialectic`) over IPC.
3. **Electron** — only worthwhile if you need a Chromium shell; heavier than Tauri for this codebase.

**Non-goal for this scaffold:** a production Electron artifact. Add a `Dockerfile` here once you pick a packaging path and CI signing requirements.

For headless smoke tests in CI, use `python -m dialectic` with fixtures under `dialectic/tests/`.
