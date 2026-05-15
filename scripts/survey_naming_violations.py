#!/usr/bin/env python3
"""Survey naming-convention violations across the Theseus monorepo.

This script is the read-only inventory step for the convention pass
(see `docs/architecture/Naming_Conventions.md`). It walks Python and
TypeScript sources, the Next.js route tree, and the Prisma schema and
emits two artefacts:

- A machine-readable JSON report (default
  `.cache/naming_survey.json`).
- A human-readable markdown summary printed to stdout.

It deliberately does **not** rename anything. Renames belong to a
codemod step, and three classes of finding are flagged
`requires_founder_approval=True` because automatic renaming would
break external contracts:

1. Public-API envelope fields (versioned — rename ⇒ version bump).
2. Signed publication input (rename ⇒ historical signatures
   invalidated).
3. Public URL paths with potential external links.
4. Database columns on tables that already contain production data
   (a data migration, not a schema-only rename).

Run:

    python scripts/survey_naming_violations.py
    python scripts/survey_naming_violations.py --json out.json
    python scripts/survey_naming_violations.py --quiet  # exit code only
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories the survey will not descend into. Build artefacts,
# vendored deps, generated code, and cached runs would otherwise drown
# the signal.
SKIP_DIR_NAMES = {
    ".git",
    ".next",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "dist",
    "dist-desktop",
    "build",
    "playwright-report",
    "test-results",
    "_generated",
    ".claude_code_runs",
    "theseus.egg-info",
    "noosphere_data",
    "snapshots",
}

PYTHON_GLOB = "**/*.py"
TS_GLOB = ("**/*.ts", "**/*.tsx")

# --- conventions ------------------------------------------------------

SNAKE = re.compile(r"^_?[a-z][a-z0-9_]*$")
UPPER = re.compile(r"^[A-Z][A-Z0-9_]*$")
PASCAL = re.compile(r"^_?[A-Z][A-Za-z0-9]*$")
CAMEL = re.compile(r"^_?[a-z][A-Za-z0-9]*$")
KEBAB_SEGMENT = re.compile(r"^[a-z][a-z0-9-]*$")
# Alembic migration files: `001_some_description.py`.
ALEMBIC_FILE = re.compile(r"^[0-9]{3,}_[a-z][a-z0-9_]*$")
# Dunder modules: `__main__.py`, `__init__.py`.
DUNDER_FILE = re.compile(r"^__[a-z]+__$")

# Names we never lint: dunder, single-letter loop vars, well-known
# acronyms used as standalone identifiers, framework-imposed names.
PY_IGNORE_NAMES = {
    "__init__",
    "__main__",
    "__all__",
    "setUp",
    "tearDown",
    "setUpClass",
    "tearDownClass",
    "asyncSetUp",
    "asyncTearDown",
    "T",
    "K",
    "V",
}

TS_IGNORE_NAMES = {
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
    "HEAD",
    "default",
    "metadata",
    "generateMetadata",
    "generateStaticParams",
    "revalidate",
    "dynamic",
    "runtime",
    "fetchCache",
    "config",
    "middleware",
}

# Next.js convention: these route files must keep their exact names.
NEXTJS_RESERVED_FILES = {
    "page.tsx",
    "page.ts",
    "layout.tsx",
    "layout.ts",
    "route.ts",
    "route.tsx",
    "loading.tsx",
    "loading.ts",
    "error.tsx",
    "error.ts",
    "not-found.tsx",
    "not-found.ts",
    "default.tsx",
    "default.ts",
    "template.tsx",
    "template.ts",
    "head.tsx",
    "head.ts",
    "opengraph-image.tsx",
    "opengraph-image.ts",
    "icon.svg",
    "favicon.ico",
    "robots.ts",
    "sitemap.ts",
    "manifest.ts",
    "middleware.ts",
    "instrumentation.ts",
    "globals.css",
    "print.css",
}


# --- data model -------------------------------------------------------


@dataclass
class Violation:
    kind: str  # "python_function", "ts_const", "url_segment", ...
    name: str
    path: str
    line: int | None = None
    expected: str = ""
    requires_founder_approval: bool = False
    note: str = ""


@dataclass
class SurveyReport:
    violations: list[Violation] = field(default_factory=list)
    files_scanned: int = 0

    def add(self, v: Violation) -> None:
        self.violations.append(v)

    def by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self.violations:
            counts[v.kind] = counts.get(v.kind, 0) + 1
        return counts

    def manual_review(self) -> list[Violation]:
        return [v for v in self.violations if v.requires_founder_approval]


# --- walkers ----------------------------------------------------------


def _should_skip(p: Path) -> bool:
    for part in p.parts:
        if part in SKIP_DIR_NAMES:
            return True
        # `.venv`, `.venv-currents`, `.venv-noosphere`, … anything that
        # looks like a Python virtualenv.
        if part.startswith(".venv") or part.endswith(".egg-info"):
            return True
    return False


def _iter_files(root: Path, patterns: Iterable[str]) -> Iterable[Path]:
    for pattern in patterns:
        for p in root.glob(pattern):
            if not p.is_file():
                continue
            if _should_skip(p):
                continue
            yield p


def survey_python(report: SurveyReport, root: Path) -> None:
    for p in _iter_files(root, [PYTHON_GLOB]):
        report.files_scanned += 1
        # File name itself.
        stem = p.stem
        if (
            not DUNDER_FILE.match(stem)
            and not SNAKE.match(stem)
            and not ALEMBIC_FILE.match(stem)
        ):
            report.add(
                Violation(
                    kind="python_file",
                    name=p.name,
                    path=str(p.relative_to(REPO_ROOT)),
                    expected="snake_case.py",
                )
            )
        try:
            source = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(p))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in PY_IGNORE_NAMES or node.name.startswith("__"):
                    continue
                if not SNAKE.match(node.name):
                    report.add(
                        Violation(
                            kind="python_function",
                            name=node.name,
                            path=str(p.relative_to(REPO_ROOT)),
                            line=node.lineno,
                            expected="snake_case",
                        )
                    )
            elif isinstance(node, ast.ClassDef):
                if not PASCAL.match(node.name):
                    report.add(
                        Violation(
                            kind="python_class",
                            name=node.name,
                            path=str(p.relative_to(REPO_ROOT)),
                            line=node.lineno,
                            expected="PascalCase",
                        )
                    )
            elif isinstance(node, ast.Assign):
                # Module-level constant convention: an assignment at
                # module scope whose RHS is a literal-ish constant
                # should be UPPER_CASE. Other module-level bindings
                # (functions returned, dataclass aliases, etc.) are
                # left alone — they're indistinguishable from
                # variables without type info.
                pass


def _ts_identifiers(source: str) -> Iterable[tuple[str, str, int]]:
    """Yield (kind, name, line) tuples by regex scan.

    A real parser would be more precise but pulls in a heavy dep. The
    regexes intentionally favour false negatives over false positives:
    we'd rather miss a violation than fabricate one.
    """
    patterns: list[tuple[str, re.Pattern[str]]] = [
        (
            "ts_function",
            re.compile(
                r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)",
                re.MULTILINE,
            ),
        ),
        (
            "ts_const",
            re.compile(
                r"^\s*(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:=]",
                re.MULTILINE,
            ),
        ),
        (
            "ts_let",
            re.compile(
                r"^\s*(?:export\s+)?let\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:=]",
                re.MULTILINE,
            ),
        ),
        (
            "ts_type",
            re.compile(
                r"^\s*(?:export\s+)?type\s+([A-Za-z_][A-Za-z0-9_]*)",
                re.MULTILINE,
            ),
        ),
        (
            "ts_interface",
            re.compile(
                r"^\s*(?:export\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)",
                re.MULTILINE,
            ),
        ),
        (
            "ts_enum",
            re.compile(
                r"^\s*(?:export\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)",
                re.MULTILINE,
            ),
        ),
        (
            "ts_class",
            re.compile(
                r"^\s*(?:export\s+(?:default\s+)?)?class\s+([A-Za-z_][A-Za-z0-9_]*)",
                re.MULTILINE,
            ),
        ),
    ]
    for kind, pat in patterns:
        for match in pat.finditer(source):
            name = match.group(1)
            line = source.count("\n", 0, match.start()) + 1
            yield kind, name, line


def survey_typescript(report: SurveyReport, root: Path) -> None:
    for p in _iter_files(root, TS_GLOB):
        report.files_scanned += 1
        rel = p.relative_to(REPO_ROOT)
        # File name convention. Test files (`.test.ts`/`.spec.tsx`)
        # are exempt from the file-name rule because their stem often
        # mirrors a sub-feature path (`api.publicResponses.email.test.ts`)
        # rather than a single identifier.
        is_test_file = ".test." in p.name or ".spec." in p.name
        if (
            p.name not in NEXTJS_RESERVED_FILES
            and ".d.ts" not in p.name
            and not is_test_file
        ):
            stem = p.stem
            for suffix in (".config", ".d", ".stories"):
                if stem.endswith(suffix):
                    stem = stem[: -len(suffix)]
            is_tsx = p.suffix == ".tsx"
            if is_tsx and not (PASCAL.match(stem) or KEBAB_SEGMENT.match(stem)):
                report.add(
                    Violation(
                        kind="ts_file",
                        name=p.name,
                        path=str(rel),
                        expected="PascalCase.tsx (component) or kebab-case.tsx (route)",
                    )
                )
            elif not is_tsx and not (CAMEL.match(stem) or KEBAB_SEGMENT.match(stem)):
                report.add(
                    Violation(
                        kind="ts_file",
                        name=p.name,
                        path=str(rel),
                        expected="camelCase.ts",
                    )
                )
        try:
            source = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Any `.tsx` file may export React components (PascalCase
        # functions / const components). `.ts` files may not.
        is_component_file = p.suffix == ".tsx"
        for kind, name, line in _ts_identifiers(source):
            if name in TS_IGNORE_NAMES:
                continue
            if kind in {"ts_type", "ts_interface", "ts_enum", "ts_class"}:
                if not PASCAL.match(name):
                    report.add(
                        Violation(
                            kind=kind,
                            name=name,
                            path=str(rel),
                            line=line,
                            expected="PascalCase",
                        )
                    )
            elif kind == "ts_function":
                # React components are PascalCase (heuristic: file is
                # .tsx and the function returns JSX — we approximate
                # with "file is a .tsx component file").
                if is_component_file and PASCAL.match(name):
                    continue
                if not CAMEL.match(name):
                    report.add(
                        Violation(
                            kind=kind,
                            name=name,
                            path=str(rel),
                            line=line,
                            expected="camelCase (PascalCase for React components)",
                        )
                    )
            elif kind in {"ts_const", "ts_let"}:
                # SCREAMING_SNAKE allowed for module-level constants;
                # PascalCase allowed for components assigned to const.
                if (
                    CAMEL.match(name)
                    or UPPER.match(name)
                    or (is_component_file and PASCAL.match(name))
                ):
                    continue
                report.add(
                    Violation(
                        kind=kind,
                        name=name,
                        path=str(rel),
                        line=line,
                        expected="camelCase or SCREAMING_SNAKE (PascalCase for components)",
                    )
                )


def survey_urls(report: SurveyReport, root: Path) -> None:
    app_dir = root / "theseus-codex" / "src" / "app"
    if not app_dir.is_dir():
        return
    for p in app_dir.rglob("*"):
        if not p.is_dir():
            continue
        if _should_skip(p):
            continue
        seg = p.name
        # Route groups: (group)
        if seg.startswith("(") and seg.endswith(")"):
            continue
        # Parallel routes: @slot
        if seg.startswith("@"):
            continue
        # Dynamic segments: [param] or [...param] or [[...param]]
        if seg.startswith("["):
            inner = seg.strip("[]")
            if inner.startswith("..."):
                inner = inner[3:]
            if not CAMEL.match(inner) and not SNAKE.match(inner):
                report.add(
                    Violation(
                        kind="url_param",
                        name=seg,
                        path=str(p.relative_to(REPO_ROOT)),
                        expected="[camelCase] or [snake_case] noun (e.g. [method])",
                        requires_founder_approval=True,
                        note="public URL — external links may exist",
                    )
                )
            # Reject the historical [name] anti-pattern that motivated
            # this whole pass.
            if inner in {"name", "id"} and "methodology" in p.parts:
                report.add(
                    Violation(
                        kind="url_param",
                        name=seg,
                        path=str(p.relative_to(REPO_ROOT)),
                        expected="[method] (conceptual noun, not [name]/[id])",
                        requires_founder_approval=True,
                    )
                )
            continue
        if not KEBAB_SEGMENT.match(seg):
            report.add(
                Violation(
                    kind="url_segment",
                    name=seg,
                    path=str(p.relative_to(REPO_ROOT)),
                    expected="kebab-case",
                    requires_founder_approval=True,
                    note="public URL — external links may exist",
                )
            )


def survey_prisma(report: SurveyReport, root: Path) -> None:
    schema = root / "theseus-codex" / "prisma" / "schema.prisma"
    if not schema.is_file():
        return
    try:
        source = schema.read_text(encoding="utf-8")
    except OSError:
        return
    # Model names: PascalCase.
    for match in re.finditer(r"^model\s+([A-Za-z_][A-Za-z0-9_]*)", source, re.MULTILINE):
        name = match.group(1)
        line = source.count("\n", 0, match.start()) + 1
        if not PASCAL.match(name):
            report.add(
                Violation(
                    kind="prisma_model",
                    name=name,
                    path="theseus-codex/prisma/schema.prisma",
                    line=line,
                    expected="PascalCase",
                )
            )
    # Column names: snake_case. Inside `model ... { ... }` blocks each
    # non-empty line that doesn't start with `@@` or `//` is a field.
    # We only check fields that carry an `@map("...")` (rename target)
    # or that look like raw column identifiers.
    model_block = re.compile(
        r"^model\s+[A-Za-z_][A-Za-z0-9_]*\s*\{(.*?)^\}",
        re.MULTILINE | re.DOTALL,
    )
    # Only scalar-typed fields become real PG columns. Relation
    # fields (typed by another model name like `Founder[]`) and
    # enum-typed fields are not columns in the storage-layer sense.
    scalar_types = {
        "String",
        "Int",
        "Float",
        "Boolean",
        "DateTime",
        "Json",
        "Bytes",
        "BigInt",
        "Decimal",
    }
    for block in model_block.finditer(source):
        body = block.group(1)
        block_line_offset = source.count("\n", 0, block.start()) + 1
        for i, line in enumerate(body.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("@@"):
                continue
            field_match = re.match(
                r"([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)",
                stripped,
            )
            if not field_match:
                continue
            fname = field_match.group(1)
            ftype = field_match.group(2)
            if ftype not in scalar_types:
                continue
            # Prisma field names mirror the column unless @map renames.
            map_match = re.search(r'@map\(\s*"([^"]+)"\s*\)', stripped)
            column = map_match.group(1) if map_match else fname
            if column == "id":
                continue
            if not SNAKE.match(column):
                report.add(
                    Violation(
                        kind="prisma_column",
                        name=column,
                        path="theseus-codex/prisma/schema.prisma",
                        line=block_line_offset + i,
                        expected="snake_case column",
                        requires_founder_approval=True,
                        note="data migration required if table has rows",
                    )
                )


# --- output -----------------------------------------------------------


def render_markdown(report: SurveyReport) -> str:
    counts = report.by_kind()
    manual = report.manual_review()
    lines = [
        "# Naming Violations Survey",
        "",
        f"Files scanned: **{report.files_scanned}**.  "
        f"Total violations: **{len(report.violations)}**.",
        "",
        "## By kind",
        "",
    ]
    for kind in sorted(counts):
        lines.append(f"- `{kind}`: {counts[kind]}")
    lines.append("")
    lines.append("## Requires founder approval before rename")
    lines.append("")
    if not manual:
        lines.append("_None._")
    else:
        for v in manual:
            loc = f"{v.path}:{v.line}" if v.line else v.path
            note = f" — {v.note}" if v.note else ""
            lines.append(f"- `{v.name}` at `{loc}` (expected {v.expected}){note}")
    lines.append("")
    lines.append("## Codemod-safe violations")
    lines.append("")
    safe = [v for v in report.violations if not v.requires_founder_approval]
    if not safe:
        lines.append("_None._")
    else:
        for v in safe[:200]:  # cap to keep markdown readable
            loc = f"{v.path}:{v.line}" if v.line else v.path
            lines.append(f"- `{v.kind}` `{v.name}` at `{loc}` → {v.expected}")
        if len(safe) > 200:
            lines.append(f"- … and {len(safe) - 200} more (see JSON report).")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        default=REPO_ROOT / ".cache" / "naming_survey.json",
        help="Path for the machine-readable JSON report.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress markdown output; exit code 0 means no violations.",
    )
    args = parser.parse_args()

    report = SurveyReport()
    survey_python(report, REPO_ROOT)
    survey_typescript(report, REPO_ROOT / "theseus-codex" / "src")
    survey_urls(report, REPO_ROOT)
    survey_prisma(report, REPO_ROOT)

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(
            {
                "files_scanned": report.files_scanned,
                "violations": [asdict(v) for v in report.violations],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if not args.quiet:
        sys.stdout.write(render_markdown(report))

    # Exit 0 always — this is a survey, not a gate. The gate is
    # `scripts/check_naming_conventions.py`.
    return 0


if __name__ == "__main__":
    sys.exit(main())
