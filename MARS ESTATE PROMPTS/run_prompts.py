#!/usr/bin/env python3
"""
run_prompts.py — execute the MARS ESTATE PROMPTS pack through Claude Code.

USAGE
    ./run_prompts.py /path/to/Mars_Estate_Dash-main
    python3 run_prompts.py /path/to/Mars_Estate_Dash-main [flags]

The script lives alongside the prompt files (00_README.txt, 01_*.txt, ...).
It discovers them via its own directory, so it works no matter where you
place the MARS ESTATE PROMPTS folder.

For each numbered prompt (in order), the script invokes:
    claude --print --output-format stream-json --verbose \
           --permission-mode bypassPermissions --add-dir <repo> \
           --model claude-opus-4-7 --effort xhigh
with the prompt piped on stdin and the Mars Estate repo as the working
directory.  Claude Code's streamed events (thinking blocks, tool calls,
tool results, text deltas, final result) are rendered to the terminal in
real time, formatted in the Mars Estate visual palette.

DEFAULTS
    model    claude-opus-4-7      Anthropic's latest Opus (released 2026-04-16)
    effort   xhigh                deepest reasoning available on Opus 4.7;
                                  recommended default for coding / agentic work.
                                  Requires Claude Code v2.1.111 or later.
                                  (Other supported levels on Opus 4.7:
                                  low, medium, high, xhigh, max.)

FLAGS
    --from NN       start at prompt NN (e.g. --from 04)
    --to   NN       stop after prompt NN
    --only NN[,NN]  run only the listed prompts (overrides --from/--to)
    --skip NN[,NN]  skip the listed prompts
    --dry-run       list prompts that WOULD run; do not invoke claude
    --model NAME    override the default model (claude-opus-4-7).  Accepts
                    either a model alias (opus, sonnet, haiku, best) or a
                    full model name (e.g. claude-sonnet-4-6, claude-opus-4-6).
    --effort LEVEL  override the default effort (xhigh).  Accepts
                    low, medium, high, xhigh, max, or auto.  Note: xhigh and
                    max are Opus-4.7-only; Claude Code falls back to the
                    highest supported level if you set one the model can't use.
    --yes           skip the pre-run confirmation prompt
    --no-color      disable ANSI color
    --max-turns N   cap claude's agent loop per prompt (default 120)
    --keep-going    do not pause for confirmation on a failed prompt
    --help          this help

REQUIREMENTS
    - Python 3.8+
    - Claude Code CLI v2.1.111 or later (for Opus 4.7 + xhigh effort):
          npm install -g @anthropic-ai/claude-code
          claude update           # if you installed earlier
          claude --login          # one time
    - ANTHROPIC_API_KEY in your environment (Claude Code reads it).

The script uses --permission-mode bypassPermissions so it can run
non-interactively.  That means Claude Code will perform edits, writes,
and shell commands without prompting.  You are opting in to this by
running the script.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Color palette — matches the Mars Estate dashboard (parchment / brass / oxblood)
# ---------------------------------------------------------------------------

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


class C:
    RESET     = "\033[0m"
    BOLD      = "\033[1m"
    DIM       = "\033[2m"
    ITALIC    = "\033[3m"

    PARCHMENT = "\033[38;5;230m"   # body text
    BRASS     = "\033[38;5;179m"   # banners, accents
    BRASS_DIM = "\033[38;5;143m"
    OXBLOOD   = "\033[38;5;131m"   # errors, warnings
    SLATE     = "\033[38;5;103m"   # thinking
    SLATE_DIM = "\033[38;5;67m"
    INK       = "\033[38;5;245m"   # metadata
    INK_DIM   = "\033[38;5;240m"
    GREEN     = "\033[38;5;108m"   # success / tool results
    YELLOW    = "\033[38;5;179m"
    CYAN      = "\033[38;5;73m"    # tool names
    MAGENTA   = "\033[38;5;132m"   # session ids


def c(text: str, *codes: str) -> str:
    """Wrap text with ANSI codes if color is enabled."""
    if not USE_COLOR or not codes:
        return text
    return "".join(codes) + text + C.RESET


# ---------------------------------------------------------------------------
# Output primitives
# ---------------------------------------------------------------------------


def hline(width: int = 76, color: str = C.BRASS_DIM) -> None:
    print(c("─" * width, color))


def banner(title: str, color: str = C.BRASS) -> None:
    line = f"  {title}"
    print()
    print(c("┌" + "─" * 76, color))
    print(c("│" + line.ljust(76), color, C.BOLD))
    print(c("└" + "─" * 76, color))


def info(text: str, *codes: str) -> None:
    print(c(text, *codes or (C.INK,)))


def detail(label: str, value: str) -> None:
    print(c(f"  {label:<10}", C.INK_DIM) + c(value, C.PARCHMENT))


def thinking(text: str) -> None:
    """Render Claude's thinking block — slate, italic, prefixed with a soft bar."""
    if not text.strip():
        return
    for line in text.rstrip().splitlines():
        prefix = c("  ┊ ", C.SLATE_DIM)
        body = c(line, C.SLATE, C.ITALIC) if USE_COLOR else line
        print(prefix + body)


def assistant_text(text: str) -> None:
    """Render assistant prose."""
    if not text.strip():
        return
    for line in text.rstrip().splitlines():
        print(c("  │ ", C.PARCHMENT) + c(line, C.PARCHMENT))


def tool_use(name: str, input_data: dict) -> None:
    """Render a tool invocation header."""
    summary = _summarize_tool_input(name, input_data)
    label = c(f"  ⚒  {name:<10}", C.CYAN, C.BOLD)
    print(label + c(summary, C.BRASS))


def tool_result(name: str, content: str, is_error: bool) -> None:
    """Render a tool result (one line, truncated)."""
    first = (content or "").strip().splitlines()
    snippet = first[0][:140] if first else ""
    if is_error:
        print(c(f"  ✗  {name or 'tool':<10}", C.OXBLOOD, C.BOLD) + c(snippet, C.OXBLOOD))
    elif snippet:
        print(c(f"  ↳  {name or 'tool':<10}", C.GREEN) + c(snippet, C.INK))


def warn(text: str) -> None:
    print(c(f"  ! {text}", C.YELLOW))


def error(text: str) -> None:
    print(c(f"  ✗ {text}", C.OXBLOOD, C.BOLD))


def success(text: str) -> None:
    print(c(f"  ✓ {text}", C.GREEN, C.BOLD))


# ---------------------------------------------------------------------------
# Tool-input summarizers — short, useful one-liners per tool kind
# ---------------------------------------------------------------------------


def _short_path(p: str, repo: Path | None = None) -> str:
    """Shorten an absolute path by stripping the repo prefix where possible."""
    if not p:
        return ""
    if repo is not None:
        try:
            rel = Path(p).resolve().relative_to(repo)
            return str(rel)
        except (ValueError, OSError):
            pass
    return p


def _summarize_tool_input(name: str, data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    if name in ("Edit", "Write", "Read", "NotebookEdit"):
        return _short_path(data.get("file_path", ""), _REPO_PATH)
    if name == "MultiEdit":
        edits = data.get("edits", [])
        return f"{_short_path(data.get('file_path', ''), _REPO_PATH)}  ({len(edits)} edits)"
    if name == "Bash":
        cmd = (data.get("command") or "").splitlines()[0]
        return cmd[:140]
    if name == "Glob":
        return f"pattern={data.get('pattern', '')}"
    if name == "Grep":
        pat = data.get("pattern", "")
        path = data.get("path", ".")
        glob = data.get("glob") or data.get("type") or ""
        extra = f"  glob={glob}" if glob else ""
        return f"{pat!r} in {_short_path(path, _REPO_PATH) or '.'}{extra}"
    if name in ("TodoWrite", "TaskCreate", "TaskUpdate"):
        return ""
    if name == "WebFetch":
        return data.get("url", "")
    if name == "WebSearch":
        return data.get("query", "")
    keys = [k for k in list(data.keys())[:3] if k not in ("description",)]
    return " ".join(f"{k}={str(data[k])[:40]}" for k in keys)


# Set during run_prompt() so summarizers can strip the repo prefix.
_REPO_PATH: Path | None = None


# ---------------------------------------------------------------------------
# Prerequisite discovery
# ---------------------------------------------------------------------------


def find_claude() -> str | None:
    """Locate the claude CLI in $PATH or common install locations."""
    p = shutil.which("claude")
    if p:
        return p
    for candidate in (
        Path.home() / ".claude" / "local" / "claude",
        Path.home() / ".local" / "bin" / "claude",
        Path("/opt/homebrew/bin/claude"),
        Path("/usr/local/bin/claude"),
    ):
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def list_prompts(script_dir: Path) -> list[tuple[str, Path]]:
    """Return numbered prompt files in sorted order. Skips 00_README.txt."""
    pattern = re.compile(r"^(\d{2})_[A-Za-z0-9_]+\.txt$")
    out: list[tuple[str, Path]] = []
    for p in sorted(script_dir.iterdir()):
        m = pattern.match(p.name)
        if not m or not p.is_file():
            continue
        num = m.group(1)
        if num == "00":
            continue  # README, not a build prompt
        out.append((num, p))
    return out


# ---------------------------------------------------------------------------
# Argument parsing — small hand-rolled parser to avoid argparse dependency wear
# ---------------------------------------------------------------------------


DEFAULT_MODEL  = "claude-opus-4-7"
DEFAULT_EFFORT = "xhigh"
VALID_EFFORTS  = {"low", "medium", "high", "xhigh", "max", "auto"}


def parse_args(argv: list[str]) -> dict:
    args = {
        "repo": None,
        "from": None,
        "to": None,
        "only": None,
        "skip": set(),
        "dry_run": False,
        "model": DEFAULT_MODEL,
        "effort": DEFAULT_EFFORT,
        "yes": False,
        "max_turns": 120,
        "keep_going": False,
    }
    i = 0
    positional: list[str] = []
    while i < len(argv):
        a = argv[i]
        if a in ("--help", "-h"):
            print(__doc__)
            sys.exit(0)
        elif a == "--from":
            args["from"] = argv[i + 1].zfill(2); i += 2
        elif a == "--to":
            args["to"] = argv[i + 1].zfill(2); i += 2
        elif a == "--only":
            args["only"] = {x.zfill(2) for x in argv[i + 1].split(",") if x}
            i += 2
        elif a == "--skip":
            args["skip"] = {x.zfill(2) for x in argv[i + 1].split(",") if x}
            i += 2
        elif a == "--dry-run":
            args["dry_run"] = True; i += 1
        elif a == "--model":
            args["model"] = argv[i + 1]; i += 2
        elif a == "--effort":
            val = argv[i + 1]
            if val not in VALID_EFFORTS:
                error(f"--effort must be one of: {', '.join(sorted(VALID_EFFORTS))}")
                sys.exit(2)
            args["effort"] = val; i += 2
        elif a == "--yes" or a == "-y":
            args["yes"] = True; i += 1
        elif a == "--no-color":
            global USE_COLOR
            USE_COLOR = False
            i += 1
        elif a == "--max-turns":
            args["max_turns"] = int(argv[i + 1]); i += 2
        elif a == "--keep-going":
            args["keep_going"] = True; i += 1
        elif a.startswith("--"):
            error(f"unknown flag: {a}")
            sys.exit(2)
        else:
            positional.append(a); i += 1

    if not positional:
        error("missing argument: path to the Mars Estate repo")
        print()
        print(c("usage:", C.BRASS, C.BOLD), f"python3 {Path(sys.argv[0]).name} /path/to/Mars_Estate_Dash-main")
        print()
        print("run with --help for the full option list.")
        sys.exit(2)
    if len(positional) > 1:
        error(f"unexpected extra argument: {positional[1]}")
        sys.exit(2)
    args["repo"] = positional[0]
    return args


# ---------------------------------------------------------------------------
# Running one prompt
# ---------------------------------------------------------------------------


def fmt_duration_ms(ms: int) -> str:
    s = ms / 1000.0
    if s < 60: return f"{s:.1f}s"
    m, rem = divmod(s, 60)
    if m < 60: return f"{int(m)}m{int(rem)}s"
    h, rem_m = divmod(m, 60)
    return f"{int(h)}h{int(rem_m)}m"


def run_prompt(
    claude_bin: str,
    prompt_path: Path,
    repo_path: Path,
    model: str | None,
    effort: str | None,
    max_turns: int,
) -> tuple[int, dict]:
    """Spawn claude on one prompt and stream its events. Returns (rc, stats)."""

    prompt_text = prompt_path.read_text(encoding="utf-8")

    # Wrap the prompt so claude knows the context.
    wrapped = (
        f"You are running a build step against the Mars Estate Dashboard repo at:\n"
        f"  {repo_path}\n\n"
        f"Read the relevant existing files in the repo (lib/db.ts, lib/chat/*, etc.) "
        f"before making changes. Follow the prompt's TASK section exactly. After making "
        f"changes, briefly state which ACCEPTANCE CRITERIA you have satisfied and which "
        f"(if any) require running commands the operator must execute themselves "
        f"(e.g. `npm run dev`).\n\n"
        f"Do not git commit. Do not run destructive commands without explicit instruction "
        f"in the prompt. If you encounter an existing file you need to modify and you are "
        f"uncertain about an existing convention, prefer reading and matching it over "
        f"guessing.\n\n"
        f"--- PROMPT BEGIN ---\n"
        f"{prompt_text}\n"
        f"--- PROMPT END ---\n"
    )

    cmd = [
        claude_bin,
        "--print",
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--add-dir", str(repo_path),
        "--max-turns", str(max_turns),
    ]
    if model:
        cmd.extend(["--model", model])
    if effort:
        cmd.extend(["--effort", effort])

    pretty = (["claude", "--print", "--output-format stream-json", "--verbose",
               "--permission-mode bypassPermissions",
               f"--add-dir {repo_path.name}",
               f"--max-turns {max_turns}"] +
              ([f"--model {model}"] if model else []) +
              ([f"--effort {effort}"] if effort else []))
    detail("exec", " ".join(pretty))
    detail("cwd", str(repo_path))

    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_path),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )

    # Send the wrapped prompt and close stdin so claude knows input is done.
    try:
        assert proc.stdin is not None
        proc.stdin.write(wrapped)
        proc.stdin.close()
    except BrokenPipeError:
        # claude may have died before consuming stdin
        pass

    stats = {
        "tool_calls": 0, "edits": 0, "writes": 0, "reads": 0,
        "bash_calls": 0, "errors": 0, "cost_usd": 0.0, "duration_ms": 0,
        "session_id": None, "num_turns": 0,
    }

    # Track tool_use ids → name so we can match results back to names.
    tool_name_by_id: dict[str, str] = {}

    assert proc.stdout is not None
    try:
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            if not line.strip():
                continue

            # The stream is JSONL.  Anything not JSON is plain text from
            # claude (rare with stream-json) — surface as a dim note.
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                info(f"  {line}", C.INK_DIM)
                continue

            etype = event.get("type")

            if etype == "system":
                if event.get("subtype") == "init":
                    sid = event.get("session_id", "")[:8]
                    if sid:
                        stats["session_id"] = sid
                        print(c(f"  session {sid}", C.MAGENTA, C.DIM))

            elif etype == "assistant":
                msg = event.get("message") or {}
                content = msg.get("content") or []
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict): continue
                        btype = block.get("type")
                        if btype == "text":
                            assistant_text(block.get("text", ""))
                        elif btype == "thinking":
                            thinking(block.get("thinking", ""))
                        elif btype == "tool_use":
                            name = block.get("name", "tool")
                            tid = block.get("id", "")
                            if tid:
                                tool_name_by_id[tid] = name
                            tool_use(name, block.get("input") or {})
                            stats["tool_calls"] += 1
                            if name == "Edit" or name == "MultiEdit": stats["edits"] += 1
                            elif name == "Write": stats["writes"] += 1
                            elif name == "Read": stats["reads"] += 1
                            elif name == "Bash": stats["bash_calls"] += 1

            elif etype == "user":
                msg = event.get("message") or {}
                content = msg.get("content") or []
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict): continue
                        if block.get("type") == "tool_result":
                            tid = block.get("tool_use_id", "")
                            tname = tool_name_by_id.get(tid, "")
                            is_err = bool(block.get("is_error"))
                            if is_err:
                                stats["errors"] += 1
                            raw_content = block.get("content", "")
                            if isinstance(raw_content, list):
                                # content can be [{type:'text', text:'...'}]
                                raw_content = " ".join(
                                    b.get("text", "") for b in raw_content
                                    if isinstance(b, dict) and b.get("type") == "text"
                                )
                            tool_result(tname, str(raw_content), is_err)

            elif etype == "result":
                # Final summary line from claude.
                stats["cost_usd"] = float(event.get("total_cost_usd", 0.0) or 0.0)
                stats["duration_ms"] = int(event.get("duration_ms", 0) or 0)
                stats["num_turns"] = int(event.get("num_turns", 0) or 0)
                if event.get("is_error") or event.get("subtype") == "error_max_turns":
                    stats["errors"] += 1
                    msg = event.get("result") or event.get("subtype") or "unknown error"
                    error(f"claude reported error: {str(msg)[:300]}")

    except KeyboardInterrupt:
        warn("interrupted; terminating claude subprocess")
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        finally:
            return 130, stats

    rc = proc.wait()
    stderr_text = ""
    if proc.stderr is not None:
        try:
            stderr_text = proc.stderr.read() or ""
        except Exception:
            stderr_text = ""
    if rc != 0:
        error(f"claude exited {rc}")
        if stderr_text.strip():
            for line in stderr_text.splitlines()[:6]:
                print(c(f"  stderr: {line}", C.OXBLOOD, C.DIM))

    return rc, stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    global _REPO_PATH

    args = parse_args(sys.argv[1:])

    script_dir = Path(__file__).resolve().parent
    repo = Path(args["repo"]).expanduser().resolve()
    _REPO_PATH = repo

    # --- prerequisite checks ---
    if not repo.exists():
        error(f"repo path does not exist: {repo}")
        return 2
    if not repo.is_dir():
        error(f"repo path is not a directory: {repo}")
        return 2
    if not (repo / "package.json").exists():
        warn(f"no package.json at {repo} — continuing, but verify the path is correct.")

    claude_bin = find_claude()
    if not claude_bin:
        error("could not find the `claude` CLI on this machine.")
        print()
        print("  install with:")
        print(c("    npm install -g @anthropic-ai/claude-code", C.PARCHMENT))
        print("  then authenticate once:")
        print(c("    claude --login", C.PARCHMENT))
        return 2

    prompts = list_prompts(script_dir)
    if not prompts:
        error(f"no prompt files found in {script_dir}")
        return 2

    # --- filter prompts ---
    if args["only"]:
        prompts = [(n, p) for n, p in prompts if n in args["only"]]
    else:
        if args["from"]:
            prompts = [(n, p) for n, p in prompts if n >= args["from"]]
        if args["to"]:
            prompts = [(n, p) for n, p in prompts if n <= args["to"]]
    if args["skip"]:
        prompts = [(n, p) for n, p in prompts if n not in args["skip"]]

    if not prompts:
        error("no prompts matched the filter")
        return 2

    # --- header ---
    banner("MARS ESTATE PROMPT RUNNER", C.BRASS)
    detail("repo",     str(repo))
    detail("prompts",  str(script_dir))
    detail("claude",   claude_bin)
    detail("count",    f"{len(prompts)} prompt(s)")
    detail("max-turns", str(args["max_turns"]))
    detail("model",     args["model"])
    detail("effort",    args["effort"])
    detail("perm",      "bypassPermissions  (claude will edit, write, and run bash without prompting)")

    if args["dry_run"]:
        banner("DRY RUN — prompts that WOULD run", C.YELLOW)
        for n, p in prompts:
            print("  " + c(n, C.BRASS, C.BOLD) + "  " + c(p.name, C.PARCHMENT))
        return 0

    # --- confirmation ---
    if not args["yes"]:
        print()
        print(c("  ABOUT TO RUN", C.BRASS, C.BOLD) +
              c(f"  {len(prompts)} prompt(s) against ", C.PARCHMENT) +
              c(str(repo), C.BRASS))
        try:
            resp = input(c("\n  Proceed? [y/N] ", C.YELLOW))
        except (EOFError, KeyboardInterrupt):
            print()
            warn("aborted before run.")
            return 130
        if resp.strip().lower() != "y":
            warn("aborted by user.")
            return 0

    # --- run loop ---
    overall = {"completed": 0, "failed": 0, "skipped": 0,
               "total_cost": 0.0, "total_duration_ms": 0,
               "started_at": time.time()}

    for idx, (n, p) in enumerate(prompts, start=1):
        # Derive a human title from the filename (e.g. 04_CLAIM_EXTRACTOR → "claim extractor")
        title_words = p.stem.split("_", 1)[1].replace("_", " ").lower() if "_" in p.stem else p.stem
        banner(f"PROMPT {n}  ({idx}/{len(prompts)})  —  {title_words}", C.BRASS)
        detail("file", p.name)
        detail("size", f"{p.stat().st_size:,} bytes")

        t0 = time.time()
        rc, stats = run_prompt(
            claude_bin=claude_bin,
            prompt_path=p,
            repo_path=repo,
            model=args["model"],
            effort=args["effort"],
            max_turns=args["max_turns"],
        )
        elapsed = time.time() - t0

        # --- per-prompt summary ---
        print()
        print(c("  ── summary ", C.BRASS_DIM) + c("─" * 65, C.BRASS_DIM))
        line = (f"  tools {stats['tool_calls']}"
                f"   edits {stats['edits']}"
                f"   writes {stats['writes']}"
                f"   reads {stats['reads']}"
                f"   bash {stats['bash_calls']}"
                f"   errors {stats['errors']}")
        print(c(line, C.INK))
        meta = (f"  cost ${stats['cost_usd']:.4f}"
                f"   claude-time {fmt_duration_ms(stats['duration_ms'])}"
                f"   wall {elapsed:.1f}s"
                f"   turns {stats['num_turns']}")
        print(c(meta, C.INK_DIM))

        overall["total_cost"] += stats["cost_usd"]
        overall["total_duration_ms"] += stats["duration_ms"]

        if rc == 0 and stats["errors"] == 0:
            overall["completed"] += 1
            success(f"prompt {n} completed cleanly")
        elif rc == 0:
            overall["completed"] += 1
            warn(f"prompt {n} finished with {stats['errors']} tool error(s) — review above")
        else:
            overall["failed"] += 1
            error(f"prompt {n} failed (exit {rc})")
            if not args["keep_going"]:
                try:
                    resp = input(c("\n  Continue with the next prompt? [y/N] ", C.YELLOW))
                except (EOFError, KeyboardInterrupt):
                    print()
                    warn("aborting run.")
                    break
                if resp.strip().lower() != "y":
                    warn("aborting run by user request.")
                    break

    # --- overall ---
    final_color = C.GREEN if overall["failed"] == 0 else C.OXBLOOD
    banner("RUN COMPLETE", final_color)
    detail("completed", str(overall["completed"]))
    if overall["failed"]:
        detail("failed",  str(overall["failed"]))
    detail("total cost", f"${overall['total_cost']:.4f}")
    detail("claude time", fmt_duration_ms(overall["total_duration_ms"]))
    detail("wall time",   f"{time.time() - overall['started_at']:.1f}s")

    print()
    if overall["failed"] == 0:
        success("done.")
        return 0
    else:
        error("done with failures.")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        warn("interrupted.")
        sys.exit(130)
