#!/usr/bin/env python3
"""
Pretty-print the Claude Code CLI's stream-json output for a human watcher.

Usage:
    claude -p --output-format stream-json --verbose --include-partial-messages \\
        | tee raw.jsonl | python3 format_stream_claude.py

Reads JSONL events from stdin, writes a human-readable trace to stdout. Every
line passes through unchanged on stderr would defeat the purpose; instead the
caller is expected to tee() the raw JSONL to a log file and pipe it through
this filter for the terminal.

The script is intentionally tolerant of unknown event shapes: anything it
does not recognise is summarised as "[<type>] <truncated repr>" rather than
dropped silently. That way an unexpected event still shows up on screen.
"""
from __future__ import annotations

import json
import sys
import textwrap
from typing import Any

MAX_INLINE = 800   # max chars per inline tool input/output preview
WRAP_WIDTH = 100   # wrap width for streaming text


def _short(s: str, n: int = MAX_INLINE) -> str:
    s = s.replace("\r", "").rstrip()
    if len(s) <= n:
        return s
    return s[:n].rstrip() + f"... [+{len(s) - n} chars]"


def _format_tool_input(name: str, inp: dict) -> str:
    # Friendly rendering for the most common Claude Code tools.
    if not isinstance(inp, dict):
        return _short(json.dumps(inp, ensure_ascii=False))

    if name in ("Read",):
        path = inp.get("file_path") or inp.get("path") or "?"
        offset = inp.get("offset")
        limit = inp.get("limit")
        extra = ""
        if offset is not None or limit is not None:
            extra = f" [offset={offset} limit={limit}]"
        return f"{path}{extra}"

    if name in ("Edit",):
        path = inp.get("file_path") or "?"
        old = (inp.get("old_string") or "").splitlines()
        new = (inp.get("new_string") or "").splitlines()
        first_old = old[0][:80] if old else ""
        first_new = new[0][:80] if new else ""
        return f"{path}\n        - {first_old}\n        + {first_new}"

    if name in ("Write",):
        path = inp.get("file_path") or "?"
        size = len(inp.get("content") or "")
        return f"{path} ({size} bytes)"

    if name in ("Bash",):
        cmd = inp.get("command") or ""
        return _short(cmd, 600)

    if name in ("Glob",):
        return f"pattern={inp.get('pattern')!r} path={inp.get('path')!r}"

    if name in ("Grep",):
        pat = inp.get("pattern")
        glob = inp.get("glob")
        path = inp.get("path")
        return f"{pat!r} glob={glob!r} path={path!r}"

    if name in ("TodoWrite",):
        todos = inp.get("todos") or []
        return f"{len(todos)} todos"

    return _short(json.dumps(inp, ensure_ascii=False, default=str))


def _emit(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _wrap_text(s: str) -> str:
    out = []
    for paragraph in s.split("\n"):
        if not paragraph:
            out.append("")
            continue
        out.append(textwrap.fill(paragraph, width=WRAP_WIDTH))
    return "\n".join(out)


def handle_event(ev: dict[str, Any], state: dict) -> None:
    t = ev.get("type")

    if t == "system":
        sub = ev.get("subtype")
        if sub == "init":
            model = ev.get("model") or "?"
            tools = ev.get("tools") or []
            cwd = ev.get("cwd") or "?"
            _emit(f"[init] model={model} cwd={cwd} tools={len(tools)}\n")
        else:
            _emit(f"[system:{sub}] {_short(json.dumps(ev, default=str), 200)}\n")
        return

    if t == "assistant":
        msg = ev.get("message") or {}
        for block in msg.get("content", []) or []:
            btype = block.get("type")
            if btype == "text":
                txt = block.get("text") or ""
                if not txt.strip():
                    continue
                if not state.get("in_text"):
                    _emit("\n")
                    state["in_text"] = True
                _emit(_wrap_text(txt))
                if not txt.endswith("\n"):
                    _emit("\n")
            elif btype == "tool_use":
                state["in_text"] = False
                name = block.get("name") or "?"
                inp = block.get("input") or {}
                _emit(f"\n  > {name}: {_format_tool_input(name, inp)}\n")
            elif btype == "thinking":
                # Optional: hide thinking by default; uncomment to show.
                # _emit("[thinking]\n")
                pass
        return

    if t == "user":
        # Tool results come back framed as user-role messages from the agent
        # loop's perspective. Surface short results, otherwise summarise.
        msg = ev.get("message") or {}
        for block in msg.get("content", []) or []:
            if block.get("type") == "tool_result":
                content = block.get("content")
                if isinstance(content, list):
                    text_parts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    out = "".join(text_parts)
                else:
                    out = content if isinstance(content, str) else json.dumps(content, default=str)
                is_error = block.get("is_error")
                marker = "  X" if is_error else "  ="
                short = _short(out, 400)
                if "\n" in short:
                    short = short.replace("\n", " | ")
                _emit(f"{marker} {short}\n")
        return

    if t == "stream_event":
        # Partial text deltas. Concatenate to terminal silently — they form
        # the same text the assistant block will eventually contain. To keep
        # the screen calm we only render deltas if no assistant block has
        # been emitted yet for this turn.
        delta = (ev.get("event") or {}).get("delta") or {}
        if delta.get("type") == "text_delta":
            txt = delta.get("text") or ""
            if not state.get("in_text"):
                state["in_text"] = True
                _emit("\n")
            _emit(txt)
        return

    if t == "result":
        sub = ev.get("subtype")
        usage = ev.get("usage") or {}
        cost = ev.get("total_cost_usd")
        dur = ev.get("duration_ms")
        if sub == "success":
            _emit(
                f"\n\n[done] duration={dur}ms cost=${cost} "
                f"input={usage.get('input_tokens')} output={usage.get('output_tokens')}\n"
            )
        else:
            _emit(f"\n[result:{sub}] {_short(json.dumps(ev, default=str), 400)}\n")
        return

    # Unknown event type — show its skeleton so we can debug.
    _emit(f"[{t}] {_short(json.dumps(ev, default=str), 200)}\n")


def main() -> int:
    state: dict[str, Any] = {"in_text": False}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            # Not JSON — pass through (e.g. claude printed an error before
            # the stream started).
            _emit(line + "\n")
            continue
        try:
            handle_event(ev, state)
        except Exception as exc:  # noqa: BLE001
            _emit(f"[formatter-error] {exc}: {_short(line, 200)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
