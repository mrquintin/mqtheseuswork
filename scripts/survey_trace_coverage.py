#!/usr/bin/env python3
"""Trace-coverage survey.

Round 17 / prompt 44 introduced span-based observability via the
``@traced`` decorator (``noosphere.observability.spans``). Prompts 45-50
were authored independently and may not have instrumented their new
public functions. This script audits which public, module-level
functions in the inquiry-layer packages are wrapped by ``@traced`` and
which are not, and writes the report to
``docs/architecture/Trace_Coverage.md``.

Why static AST analysis rather than importing the modules and inspecting
``__traced__`` at runtime: the survey must run in CI without pulling in
optional heavy deps (torch, the LLM SDKs) that some of these modules
import lazily. Parsing the source is hermetic and fast.

Surveyed surface (per the prompt — ``inquiry/``, ``temporal/``,
``literature/``, ``methods/`` post prompt 05):

* ``noosphere/inquiry`` is a re-export shim over the concrete
  inquiry-layer packages, so we survey those directly:
  ``evaluation``, ``coherence``, ``peer_review``, ``redteam``,
  ``mitigations``.
* ``temporal``, ``literature``, ``methods`` are surveyed in place.
* ``methods/_legacy`` is excluded — "post prompt 05" means the
  registry-era methods, not the pre-registry flat modules.

Usage::

    python scripts/survey_trace_coverage.py            # write the doc
    python scripts/survey_trace_coverage.py --check    # CI: exit 1 if gaps
    python scripts/survey_trace_coverage.py --stdout   # print, don't write
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NOOSPHERE_PKG = REPO_ROOT / "noosphere" / "noosphere"
DOC_PATH = REPO_ROOT / "docs" / "architecture" / "Trace_Coverage.md"

# (display label, package dir relative to noosphere/noosphere). The
# ``inquiry`` re-export shim resolves to the five concrete packages.
SURVEYED_PACKAGES: list[tuple[str, str]] = [
    ("inquiry → evaluation", "evaluation"),
    ("inquiry → coherence", "coherence"),
    ("inquiry → peer_review", "peer_review"),
    ("inquiry → redteam", "redteam"),
    ("inquiry → mitigations", "mitigations"),
    ("temporal", "temporal"),
    ("literature", "literature"),
    ("methods", "methods"),
]

# Directories under a surveyed package that are out of scope.
EXCLUDED_DIR_NAMES = {"__pycache__", "_legacy", "tests"}


@dataclass
class FunctionRecord:
    package: str
    module: str  # dotted, relative to noosphere
    qualname: str
    lineno: int
    is_traced: bool
    span_name: str | None
    sample_rate: float | None
    is_async: bool

    @property
    def source_ref(self) -> str:
        path = self.module.replace(".", "/")
        return f"noosphere/{path}.py:{self.lineno}"


def _is_traced_decorator(node: ast.expr) -> tuple[bool, str | None, float | None]:
    """Return (is_traced, span_name, sample_rate) for one decorator node.

    Handles every spelling the codebase uses:

      * ``@traced``                         — bare
      * ``@traced("span.name")``            — positional name
      * ``@traced("span.name", sample_rate=0.1)``
      * ``@obs.traced(...)`` / ``@observability.traced(...)`` — attribute
    """

    def _name_of(target: ast.expr) -> str | None:
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Attribute):
            return target.attr
        return None

    # Bare: @traced
    if _name_of(node) == "traced":
        return True, None, None

    # Called: @traced(...) / @obs.traced(...)
    if isinstance(node, ast.Call) and _name_of(node.func) == "traced":
        span_name: str | None = None
        sample_rate: float | None = None
        if node.args and isinstance(node.args[0], ast.Constant):
            value = node.args[0].value
            if isinstance(value, str):
                span_name = value
        for kw in node.keywords:
            if kw.arg == "sample_rate" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, (int, float)):
                    sample_rate = float(kw.value.value)
        return True, span_name, sample_rate

    return False, None, None


def _module_dotted(py_file: Path) -> str:
    rel = py_file.relative_to(NOOSPHERE_PKG).with_suffix("")
    return ".".join(rel.parts)


def _scan_file(py_file: Path, package: str) -> list[FunctionRecord]:
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    except (SyntaxError, UnicodeDecodeError):
        return []
    module = _module_dotted(py_file)
    records: list[FunctionRecord] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Public functions only — the survey scope is the public surface.
        if node.name.startswith("_"):
            continue
        is_traced = False
        span_name: str | None = None
        sample_rate: float | None = None
        for dec in node.decorator_list:
            traced, name, rate = _is_traced_decorator(dec)
            if traced:
                is_traced = True
                span_name = name
                sample_rate = rate
                break
        records.append(
            FunctionRecord(
                package=package,
                module=module,
                qualname=node.name,
                lineno=node.lineno,
                is_traced=is_traced,
                span_name=span_name,
                sample_rate=sample_rate,
                is_async=isinstance(node, ast.AsyncFunctionDef),
            )
        )
    return records


def _scan_package(label: str, pkg_dirname: str) -> list[FunctionRecord]:
    pkg_dir = NOOSPHERE_PKG / pkg_dirname
    if not pkg_dir.is_dir():
        return []
    records: list[FunctionRecord] = []
    for py_file in sorted(pkg_dir.rglob("*.py")):
        if any(part in EXCLUDED_DIR_NAMES for part in py_file.relative_to(pkg_dir).parts):
            continue
        # Skip private modules (``_interfaces.py``, ``_decorator.py`` …) —
        # they hold protocols and registry plumbing, not invocation surface.
        if py_file.name.startswith("_"):
            continue
        records.extend(_scan_file(py_file, label))
    return records


def survey() -> dict[str, list[FunctionRecord]]:
    """Return {package label: [FunctionRecord, …]} for every surveyed pkg."""
    out: dict[str, list[FunctionRecord]] = {}
    for label, pkg_dirname in SURVEYED_PACKAGES:
        out[label] = _scan_package(label, pkg_dirname)
    return out


def _fmt_rate(rate: float | None) -> str:
    if rate is None:
        return "1.0"
    return f"{rate:g}"


def render_markdown(results: dict[str, list[FunctionRecord]]) -> str:
    total = sum(len(v) for v in results.values())
    traced_total = sum(1 for v in results.values() for r in v if r.is_traced)
    uncovered_total = total - traced_total
    pct = (traced_total / total * 100.0) if total else 100.0

    lines: list[str] = []
    lines.append("# Trace Coverage")
    lines.append("")
    lines.append(
        "_Generated by `scripts/survey_trace_coverage.py` — do not edit by "
        "hand. Re-run the script to refresh._"
    )
    lines.append("")
    lines.append(
        f"_Last surveyed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
    )
    lines.append("")
    lines.append(
        "Round 17 / prompt 44 introduced span-based observability through the "
        "`@traced` decorator. This report audits whether the public functions "
        "added by the rest of the round are wrapped, so every method "
        "invocation, cascade traversal, and external API call shows up in the "
        "trace."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Public functions surveyed | {total} |")
    lines.append(f"| Wrapped by `@traced` | {traced_total} |")
    lines.append(f"| **Not instrumented** | **{uncovered_total}** |")
    lines.append(f"| Coverage | {pct:.1f}% |")
    lines.append("")

    if uncovered_total:
        lines.append("## Gaps — functions NOT wrapped by `@traced`")
        lines.append("")
        lines.append(
            "These public functions emit no span. Wrap them with `@traced` "
            "(add a `sample_rate` for hot-path functions called > 1k/min)."
        )
        lines.append("")
        lines.append("| Package | Function | Source |")
        lines.append("| --- | --- | --- |")
        for label, records in results.items():
            for r in sorted(records, key=lambda x: (x.module, x.lineno)):
                if not r.is_traced:
                    lines.append(
                        f"| {label} | `{r.qualname}` | `{r.source_ref}` |"
                    )
        lines.append("")
    else:
        lines.append("## Gaps")
        lines.append("")
        lines.append("None — every surveyed public function is instrumented. ✅")
        lines.append("")

    lines.append("## Full coverage by package")
    lines.append("")
    for label, records in results.items():
        pkg_traced = sum(1 for r in records if r.is_traced)
        lines.append(f"### {label} ({pkg_traced}/{len(records)} traced)")
        lines.append("")
        if not records:
            lines.append("_No public module-level functions._")
            lines.append("")
            continue
        lines.append("| Function | Traced | Span name | Sample rate | Source |")
        lines.append("| --- | --- | --- | --- | --- |")
        for r in sorted(records, key=lambda x: (x.module, x.lineno)):
            mark = "yes" if r.is_traced else "**NO**"
            span = f"`{r.span_name}`" if r.span_name else ("(default)" if r.is_traced else "—")
            rate = _fmt_rate(r.sample_rate) if r.is_traced else "—"
            lines.append(
                f"| `{r.qualname}` | {mark} | {span} | {rate} | `{r.source_ref}` |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if any surveyed public function is not traced (CI gate)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="print the report instead of writing the doc",
    )
    args = parser.parse_args(argv)

    results = survey()
    markdown = render_markdown(results)

    if args.stdout:
        sys.stdout.write(markdown)
    else:
        DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOC_PATH.write_text(markdown, encoding="utf-8")
        rel = DOC_PATH.relative_to(REPO_ROOT)
        print(f"wrote {rel}")

    total = sum(len(v) for v in results.values())
    traced_total = sum(1 for v in results.values() for r in v if r.is_traced)
    uncovered = total - traced_total
    print(f"surveyed {total} public functions · {traced_total} traced · {uncovered} gaps")

    if args.check and uncovered:
        print(f"FAIL: {uncovered} public function(s) not wrapped by @traced", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
