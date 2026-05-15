"""Cyclic-import guard for the noosphere package.

Reads two sources of truth:

* The output of ``scripts/detect_import_cycles.detect_cycles`` on the
  ``noosphere/noosphere`` tree, which reports every strongly connected
  component of size > 1 in the *top-level* import graph (function-local
  imports are deliberately ignored — they do not form a runtime cycle).
* The ``docs/architecture/Known_Cycles.md`` allowlist, which enumerates
  every cycle the team has consciously chosen to defer with a justification
  and a hard expiry date.

The test passes iff every detected SCC is listed in the allowlist *and*
its expiry date is in the future. An undocumented cycle, a cycle whose
shape has drifted from its allowlist entry, or an entry whose expiry has
passed all fail the test.

Test-only files do not count as production cycles — see
``EXCLUDED_PARTS`` in the detector.
"""

from __future__ import annotations

import datetime as _dt
import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "noosphere" / "noosphere"
KNOWN_CYCLES_DOC = REPO_ROOT / "docs" / "architecture" / "Known_Cycles.md"

# Make ``scripts/`` importable.
sys.path.insert(0, str(REPO_ROOT))

from scripts.detect_import_cycles import detect_cycles  # noqa: E402


_SLUG_RE = re.compile(r"^###\s+(\S+)\s*$")
_MODULES_RE = re.compile(r"^-\s*Modules:\s*(.*)$", re.IGNORECASE)
_EXPIRES_RE = re.compile(r"^-\s*Expires:\s*(\d{4}-\d{2}-\d{2})\s*$", re.IGNORECASE)


def _parse_known_cycles(text: str) -> dict[tuple[str, ...], _dt.date]:
    """Return ``{sorted-module-tuple: expiry_date}`` for every block in
    ``Known_Cycles.md``. A block is delimited by a ``### slug`` heading;
    inside it, the ``Modules:`` line lists the SCC members (comma- or
    newline-separated) and the ``Expires:`` line carries the expiry."""
    entries: dict[tuple[str, ...], _dt.date] = {}
    current_slug: str | None = None
    current_modules: list[str] = []
    current_modules_open = False
    current_expiry: _dt.date | None = None

    def _finalize() -> None:
        nonlocal current_slug, current_modules, current_expiry, current_modules_open
        if current_slug and current_modules and current_expiry is not None:
            cleaned = tuple(sorted(m.strip().rstrip(",") for m in current_modules if m.strip()))
            if cleaned:
                entries[cleaned] = current_expiry
        current_slug = None
        current_modules = []
        current_modules_open = False
        current_expiry = None

    for raw in text.splitlines():
        slug_match = _SLUG_RE.match(raw)
        if slug_match:
            _finalize()
            current_slug = slug_match.group(1)
            continue
        if current_slug is None:
            continue
        mod_match = _MODULES_RE.match(raw)
        if mod_match:
            current_modules_open = True
            rest = mod_match.group(1).strip()
            if rest:
                current_modules.extend(p for p in rest.split(",") if p.strip())
            continue
        exp_match = _EXPIRES_RE.match(raw)
        if exp_match:
            current_modules_open = False
            current_expiry = _dt.date.fromisoformat(exp_match.group(1))
            continue
        # If the Modules: line spilled across multiple lines (the doc
        # writes one module per line for readability), keep absorbing
        # bare module names that look like ``noosphere.foo.bar``.
        if current_modules_open:
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("-"):  # next field
                current_modules_open = False
                continue
            current_modules.extend(p for p in stripped.split(",") if p.strip())
    _finalize()
    return entries


def _detected_sccs() -> list[tuple[str, ...]]:
    cycles = detect_cycles(str(PACKAGE_ROOT), package="noosphere")
    return [tuple(sorted(c)) for c in cycles]


def test_known_cycles_doc_parses() -> None:
    """The allowlist itself must be parseable. If this fails, the rest of
    the assertions below would silently degrade to 'no allowlist'."""
    assert KNOWN_CYCLES_DOC.is_file(), f"missing {KNOWN_CYCLES_DOC}"
    entries = _parse_known_cycles(KNOWN_CYCLES_DOC.read_text(encoding="utf-8"))
    assert entries, "Known_Cycles.md parsed to zero entries"


def test_every_detected_cycle_is_allowlisted() -> None:
    """No cycle may appear in the graph that is not documented."""
    allow = _parse_known_cycles(KNOWN_CYCLES_DOC.read_text(encoding="utf-8"))
    detected = _detected_sccs()
    undocumented = [scc for scc in detected if scc not in allow]
    assert not undocumented, (
        "Undocumented import cycle(s) detected. "
        "Either remove the cycle structurally (preferred) or add an entry "
        "to docs/architecture/Known_Cycles.md with a future expiry date.\n\n"
        + "\n".join("  - " + ", ".join(scc) for scc in undocumented)
    )


def test_no_expired_allowlist_entries() -> None:
    """A listed cycle whose expiry has passed must be re-justified or fixed."""
    today = _dt.date.today()
    allow = _parse_known_cycles(KNOWN_CYCLES_DOC.read_text(encoding="utf-8"))
    expired = {scc: exp for scc, exp in allow.items() if exp < today}
    assert not expired, (
        "Allowlist entries in Known_Cycles.md have expired. Either fix the "
        "cycle structurally or extend the expiry with a written reason.\n\n"
        + "\n".join(
            f"  - expired {exp.isoformat()}: " + ", ".join(scc)
            for scc, exp in expired.items()
        )
    )


def test_no_stale_allowlist_entries() -> None:
    """An allowlist entry that no longer matches any detected cycle is stale —
    delete it so the document does not accrue cruft.

    Stale here means: the exact sorted-module tuple is no longer reported
    as an SCC by the detector. A cycle that shrank still surfaces as a
    different tuple, which fails ``test_every_detected_cycle_is_allowlisted``
    above and prompts a rewrite of the entry."""
    allow = _parse_known_cycles(KNOWN_CYCLES_DOC.read_text(encoding="utf-8"))
    detected = set(_detected_sccs())
    stale = [scc for scc in allow if scc not in detected]
    assert not stale, (
        "Allowlist entries in Known_Cycles.md no longer match any detected "
        "cycle. Delete the obsolete entries.\n\n"
        + "\n".join("  - " + ", ".join(scc) for scc in stale)
    )


@pytest.mark.parametrize(
    "scc",
    _detected_sccs() or [pytest.param((), marks=pytest.mark.skip(reason="no cycles"))],
)
def test_cycle_members_are_real_modules(scc: tuple[str, ...]) -> None:
    """Defence-in-depth: every module named in a detected SCC must exist on
    disk. Catches the case where the detector hallucinated a module from a
    malformed import statement."""
    for module in scc:
        rel = module.replace(".", "/")
        as_file = PACKAGE_ROOT.parent / f"{rel}.py"
        as_pkg = PACKAGE_ROOT.parent / rel / "__init__.py"
        assert as_file.is_file() or as_pkg.is_file(), (
            f"detected cycle includes {module!r} which is not a real module"
        )
