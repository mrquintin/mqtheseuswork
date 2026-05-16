#!/usr/bin/env python3
"""Doc-freshness check.

For every Markdown file under ``docs/``, ``coding_prompts/``, and the
repo root:

* Parses every relative link ``[text](path)`` and every image
  reference ``![alt](path)`` (including ``<img src="path">``).
* Asserts the target file exists.
* For images: asserts size < 5 MB.

For the README's "Surface map" section, parses listed routes and
asserts each exists at the documented path under
``theseus-codex/src/app/`` (a route ``/foo/bar`` resolves to
``theseus-codex/src/app/foo/bar/page.tsx`` or
``theseus-codex/src/app/foo/bar/route.ts``). The surface map check
is OPT-IN: it only fires when both the README section and the app
tree exist.

External links (``http://``, ``https://``, ``mailto:``) are ignored.
An allowlist at ``.github/doc_freshness_allowlist.txt`` carries
known-broken paths that we accept for reasons spelled out in that
file's header.

Exit 0 on clean, non-zero on any drift (unless ``--report-only``).
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = REPO_ROOT / ".github" / "doc_freshness_allowlist.txt"
SURFACE_MAP_HEADING = "Surface map"
APP_ROOT = REPO_ROOT / "theseus-codex" / "src" / "app"
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Where we look for markdown.
MD_ROOTS_RELATIVE = ["docs", "coding_prompts"]
# Plus all top-level *.md files at REPO_ROOT.

LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMG_TAG_RE = re.compile(r"<img\s+[^>]*src=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)


@dataclasses.dataclass
class DocFinding:
    file: pathlib.Path
    line: int
    code: str
    message: str

    def render(self, root: pathlib.Path) -> str:
        rel = self.file.relative_to(root) if self.file.is_absolute() else self.file
        return f"  {rel}:{self.line} [{self.code}] {self.message}"


def _load_allowlist(path: pathlib.Path = ALLOWLIST_PATH) -> set[str]:
    if not path.is_file():
        return set()
    out: set[str] = set()
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.add(s)
    return out


def _iter_markdown_files(root: pathlib.Path) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for top in MD_ROOTS_RELATIVE:
        d = root / top
        if d.is_dir():
            out.extend(sorted(d.rglob("*.md")))
    out.extend(sorted(root.glob("*.md")))
    return out


def _is_external(target: str) -> bool:
    return (
        target.startswith("http://")
        or target.startswith("https://")
        or target.startswith("mailto:")
        or target.startswith("tel:")
        or target.startswith("#")
    )


def _resolve_link(md_file: pathlib.Path, target: str) -> pathlib.Path:
    # Strip URL fragments and queries — `intro.md#section` -> `intro.md`.
    clean = target.split("#", 1)[0].split("?", 1)[0]
    if clean.startswith("/"):
        # Absolute (project-root) path.
        return REPO_ROOT / clean.lstrip("/")
    return (md_file.parent / clean).resolve()


def _is_in_app_route(target: str) -> bool:
    """A path like ``/principles/foo`` is a route in the Codex web app
    rather than a filesystem path. Treat it as resolved if a matching
    page exists under ``theseus-codex/src/app/`` — otherwise the
    filesystem-absolute fallback runs.
    """
    if not target.startswith("/"):
        return False
    # File-shaped paths (with extension or a real on-disk hit) get the
    # filesystem treatment via the caller.
    head = target.split("#", 1)[0].split("?", 1)[0]
    if "." in pathlib.Path(head).name:
        return False
    return _route_exists(head)


def _check_markdown_file(
    md_file: pathlib.Path,
    allowlist: set[str],
    max_image_bytes: int = MAX_IMAGE_BYTES,
) -> list[DocFinding]:
    findings: list[DocFinding] = []
    try:
        text = md_file.read_text(errors="replace")
    except OSError as exc:
        return [DocFinding(md_file, 0, "READ_FAILED", str(exc))]

    for i, line in enumerate(text.splitlines(), start=1):
        # Skip fenced-code lines? Quick check: count leading triple-backticks.
        # For simplicity we let the regex apply — the link syntax rarely
        # appears inside code blocks in this repo.
        for m in LINK_RE.finditer(line):
            bang, _, target = m.group(1), m.group(2), m.group(3)
            if _is_external(target):
                continue
            if target in allowlist:
                continue
            # Web-route paths like `/principles/foo` resolve to Next.js
            # pages, not filesystem entries.
            if _is_in_app_route(target):
                continue
            resolved = _resolve_link(md_file, target)
            if not resolved.exists():
                findings.append(
                    DocFinding(
                        md_file,
                        i,
                        "LINK_BROKEN",
                        f"target {target!r} does not exist (resolved {resolved})",
                    )
                )
                continue
            if bang == "!" and resolved.is_file():
                try:
                    size = resolved.stat().st_size
                except OSError:
                    continue
                if size > max_image_bytes:
                    findings.append(
                        DocFinding(
                            md_file,
                            i,
                            "IMAGE_TOO_LARGE",
                            f"image {target!r} is {size} bytes "
                            f"(> {max_image_bytes})",
                        )
                    )
        for m in IMG_TAG_RE.finditer(line):
            target = m.group(1)
            if _is_external(target) or target in allowlist:
                continue
            resolved = _resolve_link(md_file, target)
            if not resolved.exists():
                findings.append(
                    DocFinding(
                        md_file,
                        i,
                        "IMG_TAG_BROKEN",
                        f"<img src={target!r}> does not exist",
                    )
                )
    return findings


_SURFACE_HEADING_RE = re.compile(r"^\s{0,3}#{2,6}\s+Surface\s+map\s*$", re.IGNORECASE)
_BULLET_ROUTE_RE = re.compile(r"^\s*[-*]\s+`?(/[A-Za-z0-9_/\-\[\]]*)`?")


def _extract_surface_routes(readme_text: str) -> list[tuple[int, str]]:
    """Return [(line_number, route)] from the Surface map section."""
    lines = readme_text.splitlines()
    in_section = False
    out: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        if _SURFACE_HEADING_RE.match(line):
            in_section = True
            continue
        if in_section and re.match(r"^\s{0,3}#{1,6}\s+", line):
            # Next heading ends the section.
            break
        if in_section:
            m = _BULLET_ROUTE_RE.match(line)
            if m:
                out.append((i, m.group(1)))
    return out


def _resolve_route_dir(
    root: pathlib.Path, parts: list[str]
) -> pathlib.Path | None:
    """Walk the Next.js app tree, treating ``[...]`` segments as
    wildcards. Returns the directory holding ``page.tsx``/``route.ts``
    if one matches, else None.
    """
    cur = [root]
    for part in parts:
        nxt: list[pathlib.Path] = []
        for d in cur:
            # Direct match.
            direct = d / part
            if direct.is_dir():
                nxt.append(direct)
            # Dynamic [slug] / [id] / [...rest].
            if d.is_dir():
                for child in d.iterdir():
                    if (
                        child.is_dir()
                        and child.name.startswith("[")
                        and child.name.endswith("]")
                    ):
                        nxt.append(child)
        cur = nxt
        if not cur:
            return None
    for d in cur:
        if (d / "page.tsx").is_file() or (d / "route.ts").is_file():
            return d
    return None


def _route_exists(route: str) -> bool:
    """A route like ``/foo/bar`` resolves to ``.../app/foo/bar/page.tsx``
    (or ``.../route.ts`` for API routes). Dynamic segments under the
    app tree (``[slug]``, ``[id]``, ``[...rest]``) match any literal
    URL segment. Route groups like ``(authed)`` are transparent.
    """
    if not APP_ROOT.is_dir():
        return True  # nothing to enforce; section is opt-in
    parts = [p for p in route.strip("/").split("/") if p]
    # Try resolution from app root directly, plus from each route
    # group (``(authed)``, ``(home)``, ...) since those are URL-
    # transparent in Next.js.
    roots = [APP_ROOT]
    for entry in APP_ROOT.iterdir():
        if entry.is_dir() and entry.name.startswith("(") and entry.name.endswith(")"):
            roots.append(entry)
    if not parts:
        return any((r / "page.tsx").is_file() for r in roots)
    return any(_resolve_route_dir(r, parts) is not None for r in roots)


def _check_surface_map(readme: pathlib.Path) -> list[DocFinding]:
    if not readme.is_file():
        return []
    text = readme.read_text(errors="replace")
    if not _SURFACE_HEADING_RE.search(text):
        # Section absent — opt-in, so nothing to enforce.
        return []
    if not APP_ROOT.is_dir():
        return []
    findings: list[DocFinding] = []
    routes = _extract_surface_routes(text)
    for line_no, route in routes:
        if not _route_exists(route):
            findings.append(
                DocFinding(
                    readme,
                    line_no,
                    "SURFACE_MAP_DRIFT",
                    f"README lists route {route!r} but no page.tsx/route.ts "
                    "exists under theseus-codex/src/app/",
                )
            )
    return findings


def check(
    root: pathlib.Path = REPO_ROOT,
    allowlist_path: pathlib.Path = ALLOWLIST_PATH,
) -> tuple[int, list[DocFinding]]:
    allowlist = _load_allowlist(allowlist_path)
    findings: list[DocFinding] = []
    for md in _iter_markdown_files(root):
        findings.extend(_check_markdown_file(md, allowlist))
    findings.extend(_check_surface_map(root / "README.md"))
    return (1 if findings else 0, findings)


def _print_report(findings: list[DocFinding], root: pathlib.Path) -> None:
    if not findings:
        print("Doc freshness: OK (no broken links, no oversized images).")
        return
    by_file: dict[pathlib.Path, list[DocFinding]] = {}
    for f in findings:
        by_file.setdefault(f.file, []).append(f)
    for f_path in sorted(by_file):
        try:
            rel = f_path.relative_to(root)
        except ValueError:
            rel = f_path
        print(f"\n=== {rel} ===")
        for f in by_file[f_path]:
            print(f"  L{f.line} [{f.code}] {f.message}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repository root (default: this script's parent of parents).",
    )
    p.add_argument(
        "--allowlist",
        default=str(ALLOWLIST_PATH),
        help="Path to the known-broken allowlist.",
    )
    p.add_argument(
        "--report-only",
        action="store_true",
        help="Print the report but always exit 0.",
    )
    p.add_argument(
        "--paths",
        nargs="+",
        default=None,
        help="Only check the given markdown paths (relative to root).",
    )
    args = p.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    if args.paths:
        allowlist = _load_allowlist(pathlib.Path(args.allowlist))
        findings: list[DocFinding] = []
        for raw in args.paths:
            md = (root / raw).resolve() if not pathlib.Path(raw).is_absolute() else pathlib.Path(raw)
            if not md.is_file() or md.suffix != ".md":
                continue
            findings.extend(_check_markdown_file(md, allowlist))
        # Always re-check the surface map if README was in the list.
        if any(pathlib.Path(p).name == "README.md" for p in args.paths):
            findings.extend(_check_surface_map(root / "README.md"))
        _print_report(findings, root)
        return 0 if args.report_only else (1 if findings else 0)
    rc, findings = check(root=root, allowlist_path=pathlib.Path(args.allowlist))
    _print_report(findings, root)
    return 0 if args.report_only else rc


if __name__ == "__main__":
    sys.exit(main())
