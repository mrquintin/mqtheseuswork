#!/usr/bin/env python3
"""
cc_stream_formatter.py — pretty-print Claude Code's --output-format stream-json.

Reads NDJSON events on stdin, writes a human-readable running narrative to
stdout. Intended to be piped in front of `tee`:

    claude --print --verbose --output-format stream-json ... \
        | tee raw.jsonl \
        | python3 cc_stream_formatter.py \
        | tee pretty.log

Behavior:
  - assistant text  → streamed inline as it arrives (token-level)
  - tool calls      → "→ ToolName  <brief args>" with timestamp
  - tool results    → "✓ <size> <preview>" or "✗ <error snippet>"
  - thinking blocks → shown dimmed, truncated
  - session start   → banner with model + cwd
  - final result    → summary with turns / elapsed / cost
"""
import json
import sys
from datetime import datetime

USE_COLOR = sys.stdout.isatty()

def _c(code: str) -> str:
    return f"\033[{code}m" if USE_COLOR else ""

RESET   = _c("0")
BOLD    = _c("1")
DIM     = _c("2")
RED     = _c("31")
GREEN   = _c("32")
YELLOW  = _c("33")
BLUE    = _c("34")
MAGENTA = _c("35")
CYAN    = _c("36")


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def truncate(s, n: int = 100) -> str:
    s = str(s).replace("\n", " ⏎ ")
    return s if len(s) <= n else s[: n - 1] + "…"


def summarize_tool_input(name: str, inp) -> str:
    """One-line sketch of a tool call's arguments."""
    if not isinstance(inp, dict):
        return truncate(inp)
    if name in ("Read", "Write"):
        return inp.get("file_path", "")
    if name == "Edit":
        path = inp.get("file_path", "")
        old = truncate(inp.get("old_string", ""), 40)
        return f"{path}   «{old}»"
    if name == "Bash":
        return truncate(inp.get("command", ""), 140)
    if name == "Glob":
        return inp.get("pattern", "")
    if name == "Grep":
        pat = inp.get("pattern", "")
        path = inp.get("path", ".")
        return f"{pat!r} in {path}"
    if name in ("TodoWrite",):
        todos = inp.get("todos", [])
        if todos:
            active = next(
                (t.get("content", "") for t in todos if t.get("status") == "in_progress"),
                "",
            )
            return f"{len(todos)} todos — active: {truncate(active, 60)}"
    if name == "WebFetch":
        return inp.get("url", "")
    if name == "WebSearch":
        return inp.get("query", "")
    # generic: first two keys
    parts = []
    for k, v in list(inp.items())[:2]:
        parts.append(f"{k}={truncate(v, 40)}")
    return ", ".join(parts)


def extract_tool_result_text(body) -> str:
    if isinstance(body, list):
        return "\n".join(
            b.get("text", "") for b in body if isinstance(b, dict)
        )
    return str(body or "")


# --- streaming state --------------------------------------------------------

_text_active = False


def _end_text_stream():
    global _text_active
    if _text_active:
        sys.stdout.write("\n")
        sys.stdout.flush()
        _text_active = False


def _emit_event(marker: str, color: str, label: str, detail: str = ""):
    _end_text_stream()
    line = f"{DIM}[{ts()}]{RESET} {color}{marker} {label}{RESET}"
    if detail:
        line += f" {DIM}{detail}{RESET}"
    print(line)
    sys.stdout.flush()


def _emit_text_delta(text: str):
    global _text_active
    if not _text_active:
        sys.stdout.write(f"\n{BLUE}Claude:{RESET} ")
        _text_active = True
    sys.stdout.write(text)
    sys.stdout.flush()


# --- event dispatch ---------------------------------------------------------

def handle_assistant(msg):
    content = (msg or {}).get("content") or []
    for block in content:
        btype = block.get("type")
        if btype == "text":
            txt = block.get("text", "")
            if txt:
                _emit_text_delta(txt)
        elif btype == "thinking":
            thought = block.get("thinking", "")
            if thought:
                _emit_event("~", MAGENTA, "thinking", truncate(thought, 180))
        elif btype == "tool_use":
            name = block.get("name", "?")
            inp = block.get("input", {}) or {}
            _emit_event("→", YELLOW, name, summarize_tool_input(name, inp))


def handle_user(msg):
    content = (msg or {}).get("content") or []
    for block in content:
        if block.get("type") == "tool_result":
            is_error = bool(block.get("is_error"))
            body = extract_tool_result_text(block.get("content"))
            lines = body.count("\n") + 1 if body else 0
            size = f"{lines} line{'s' if lines != 1 else ''}"
            if is_error:
                _emit_event("✗", RED, "tool error", truncate(body, 180))
            else:
                _emit_event("✓", GREEN, "result", f"{size}: {truncate(body, 140)}")


def handle_result(ev):
    subtype = ev.get("subtype", "")
    dur_ms = ev.get("duration_ms", 0) or 0
    cost = ev.get("total_cost_usd", 0) or 0
    turns = ev.get("num_turns", 0) or 0
    color = GREEN if subtype == "success" else RED
    detail = f"turns={turns}  elapsed={dur_ms / 1000:.1f}s"
    if cost:
        detail += f"  cost=${cost:.4f}"
    _emit_event("◼", color, f"prompt {subtype or 'done'}", detail)


def handle_system(ev):
    subtype = ev.get("subtype", "")
    if subtype == "init":
        model = ev.get("model", "?")
        cwd = ev.get("cwd", "?")
        sid = ev.get("session_id", "?")[:8]
        _emit_event(
            "●", CYAN, "session started",
            f"model={model}  cwd={cwd}  session={sid}",
        )


def main():
    for raw in sys.stdin:
        raw = raw.rstrip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            _emit_event("?", DIM, "unparsed", truncate(raw, 160))
            continue

        etype = ev.get("type")
        try:
            if etype == "system":
                handle_system(ev)
            elif etype == "assistant":
                handle_assistant(ev.get("message"))
            elif etype == "user":
                handle_user(ev.get("message"))
            elif etype == "result":
                handle_result(ev)
            else:
                # stream control frame or unknown — show minimally
                _emit_event("·", DIM, etype or "?", truncate(json.dumps(ev), 140))
        except Exception as e:  # noqa: BLE001 — formatter must never crash the pipeline
            _emit_event("!", RED, "formatter error", f"{type(e).__name__}: {e}")

    _end_text_stream()


if __name__ == "__main__":
    main()
