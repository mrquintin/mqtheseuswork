#!/usr/bin/env python3
"""Pretty-print Claude Code's --output-format stream-json events as they arrive.

Reads NDJSON from stdin. For each event, prints a colored, compact one-line summary
identifying what Claude Code is doing (reading/writing files, running bash, speaking).

Full raw JSON is NOT printed here — the caller should tee stdin to a log file if they
want it preserved for later inspection.
"""
from __future__ import annotations

import json
import sys

BLUE = "\033[0;34m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
MAGENTA = "\033[0;35m"
CYAN = "\033[0;36m"
DIM = "\033[2m"
NC = "\033[0m"


def trunc(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def handle_assistant(ev: dict) -> None:
    message = ev.get("message") or {}
    for block in message.get("content", []) or []:
        btype = block.get("type")
        if btype == "text":
            text = (block.get("text") or "").strip()
            if text:
                print(f"{GREEN}[say]{NC}   {trunc(text, 400)}")
        elif btype == "tool_use":
            name = block.get("name") or "?"
            inp = block.get("input") or {}
            label = name.lower()
            if label == "read":
                print(f"{BLUE}[read]{NC}  {inp.get('file_path', '?')}")
            elif label in ("write",):
                path = inp.get("file_path", "?")
                size = len(inp.get("content") or "")
                print(f"{YELLOW}[write]{NC} {path} {DIM}({size} chars){NC}")
            elif label == "edit":
                path = inp.get("file_path", "?")
                print(f"{YELLOW}[edit]{NC}  {path}")
            elif label == "bash":
                cmd = trunc(inp.get("command") or "", 160)
                print(f"{CYAN}[bash]{NC}  {cmd}")
            elif label == "glob":
                pat = inp.get("pattern") or "?"
                print(f"{DIM}[glob]{NC}  {pat}")
            elif label == "grep":
                pat = inp.get("pattern") or "?"
                path = inp.get("path") or inp.get("glob") or ""
                print(f"{DIM}[grep]{NC}  {trunc(pat, 80)}  {DIM}{trunc(path, 60)}{NC}")
            elif label in ("todowrite", "todo_write"):
                todos = inp.get("todos") or []
                print(f"{MAGENTA}[todo]{NC}  {len(todos)} task(s)")
            elif label in ("webfetch", "web_fetch", "websearch", "web_search"):
                url = inp.get("url") or inp.get("query") or ""
                print(f"{DIM}[{label}]{NC} {trunc(url, 140)}")
            else:
                preview = trunc(json.dumps(inp, ensure_ascii=False), 140)
                print(f"{DIM}[{label}]{NC} {preview}")


def handle_user(ev: dict) -> None:
    """User-role events inside stream-json are typically tool_results Claude receives.
    We print a short confirmation without the full result body.
    """
    message = ev.get("message") or {}
    for block in message.get("content", []) or []:
        if block.get("type") == "tool_result":
            # Content is a string or list of parts; summarize size only
            content = block.get("content")
            if isinstance(content, list):
                size = sum(len(p.get("text", "")) if isinstance(p, dict) else len(str(p)) for p in content)
            else:
                size = len(str(content or ""))
            is_error = block.get("is_error")
            tag = "err" if is_error else "ok"
            color = RED if is_error else DIM
            print(f"{color}[{tag}]{NC}   {DIM}tool result, {size} chars{NC}")


def handle_result(ev: dict) -> None:
    subtype = ev.get("subtype")
    tokens_in = ev.get("usage", {}).get("input_tokens") or ev.get("input_tokens")
    tokens_out = ev.get("usage", {}).get("output_tokens") or ev.get("output_tokens")
    cost = ev.get("total_cost_usd") or ev.get("cost_usd")
    duration_ms = ev.get("duration_ms")
    bits = []
    if tokens_in is not None:
        bits.append(f"in={tokens_in}")
    if tokens_out is not None:
        bits.append(f"out={tokens_out}")
    if cost is not None:
        bits.append(f"${cost:.4f}")
    if duration_ms is not None:
        bits.append(f"{duration_ms // 1000}s")
    suffix = " ".join(bits)
    print(f"{MAGENTA}[done]{NC}  subtype={subtype} {DIM}{suffix}{NC}")


def handle_system(ev: dict) -> None:
    subtype = ev.get("subtype")
    if subtype == "init":
        model = ev.get("model") or ""
        tools = ev.get("tools") or []
        print(f"{DIM}[init]{NC}  model={model} tools={len(tools)}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            # Not JSON — likely a warning from Claude Code; pass through
            print(f"{DIM}{trunc(line, 200)}{NC}")
            continue
        etype = ev.get("type")
        if etype == "assistant":
            handle_assistant(ev)
        elif etype == "user":
            handle_user(ev)
        elif etype == "result":
            handle_result(ev)
        elif etype == "system":
            handle_system(ev)
        else:
            # Unknown event type — show compactly
            print(f"{DIM}[{etype or '?'}] {trunc(json.dumps(ev, ensure_ascii=False), 160)}{NC}")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
