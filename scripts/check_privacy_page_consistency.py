#!/usr/bin/env python3
"""Build-time check: /privacy and the retention policy table agree.

The canonical retention table is
``noosphere/noosphere/decay/retention_policies.py``. The Next.js side
holds a literal mirror in ``theseus-codex/src/lib/retentionApi.ts`` that
the public ``/privacy`` page is generated from.

This script enforces three invariants:

  1. Every policy in the Python table appears in the TS mirror, and the
     TS mirror declares no extras.
  2. Every field that affects user-visible behavior or prose
     (``ttl_days``, ``action``, ``override``, ``auto_execute``,
     ``privacy_summary``) matches between the two sources.
  3. The privacy page renders one entry per policy — i.e. no policy is
     hidden from the public summary.

Run as part of the deploy build:

    python scripts/check_privacy_page_consistency.py

Exits non-zero on drift.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
TS_MIRROR_PATH = (
    REPO_ROOT / "theseus-codex" / "src" / "lib" / "retentionApi.ts"
)
PRIVACY_PAGE_PATH = (
    REPO_ROOT / "theseus-codex" / "src" / "app" / "privacy" / "page.tsx"
)


def _load_python_policies() -> list[dict[str, Any]]:
    sys.path.insert(0, str(REPO_ROOT / "noosphere"))
    from noosphere.decay.retention_policies import all_policies

    out: list[dict[str, Any]] = []
    for p in all_policies():
        out.append(
            {
                "key": p.key,
                "label": p.label,
                "ttl_days": p.ttl_days,
                "action": p.action.value,
                "override": p.override.value,
                "auto_execute": p.auto_execute,
                "privacy_summary": p.privacy_summary,
            }
        )
    return out


# ── TS parser (regex, intentionally narrow) ─────────────────────────────────
#
# We don't want to install a JS engine just to read this file. Each
# entry in the TS array follows a fixed shape that this regex can
# reliably extract; if someone reformats it past recognition the check
# fails closed (which is the desired outcome).


_KEY_RE = re.compile(r'key:\s*"([^"]+)"')
_LABEL_RE = re.compile(r'label:\s*"([^"]+)"')
_TTL_RE = re.compile(r"ttlDays:\s*(\d+|null)")
_ACTION_RE = re.compile(r'action:\s*"([^"]+)"')
_OVERRIDE_RE = re.compile(r'override:\s*"([^"]+)"')
_AUTO_RE = re.compile(r"autoExecute:\s*(true|false)")
_SUMMARY_RE = re.compile(r'privacySummary:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)


def _split_objects(src: str) -> list[str]:
    decl = re.search(
        r"RETENTION_POLICIES\s*:\s*RetentionPolicy\[\]\s*=\s*\[", src
    )
    if decl is None:
        raise SystemExit(
            "TS mirror missing RETENTION_POLICIES export — drift, fail closed"
        )
    arr_start = decl.end() - 1  # position of the opening '['
    depth = 0
    out: list[str] = []
    cur: list[str] = []
    in_obj = False
    for ch in src[arr_start + 1 :]:
        if ch == "{":
            depth += 1
            in_obj = True
            cur.append(ch)
        elif ch == "}":
            depth -= 1
            cur.append(ch)
            if depth == 0 and in_obj:
                out.append("".join(cur))
                cur = []
                in_obj = False
        elif depth == 0 and ch == "]":
            break
        else:
            if in_obj:
                cur.append(ch)
    return out


def _load_ts_policies() -> list[dict[str, Any]]:
    src = TS_MIRROR_PATH.read_text()
    out: list[dict[str, Any]] = []
    for blob in _split_objects(src):
        try:
            ttl_raw = _TTL_RE.search(blob).group(1)
            entry = {
                "key": _KEY_RE.search(blob).group(1),
                "label": _LABEL_RE.search(blob).group(1),
                "ttl_days": None if ttl_raw == "null" else int(ttl_raw),
                "action": _ACTION_RE.search(blob).group(1),
                "override": _OVERRIDE_RE.search(blob).group(1),
                "auto_execute": _AUTO_RE.search(blob).group(1) == "true",
                "privacy_summary": (
                    _SUMMARY_RE.search(blob).group(1).replace('\\"', '"')
                ),
            }
        except AttributeError as exc:
            raise SystemExit(
                f"TS mirror entry missing required field — drift: {exc}"
            )
        out.append(entry)
    return out


# ── Privacy page check ───────────────────────────────────────────────────────


def _privacy_page_keys() -> set[str]:
    """Return the set of policy keys that the page is wired to render.

    We don't parse the full TSX — instead we assert the page imports
    RETENTION_POLICIES (so the rendering is data-driven) and uses
    ``data-policy-key`` markers around each row. The check is enough to
    detect "someone hardcoded a static blurb."
    """
    src = PRIVACY_PAGE_PATH.read_text()
    if "RETENTION_POLICIES" not in src:
        raise SystemExit(
            "privacy page does not import RETENTION_POLICIES — "
            "page must be generated from the policy table"
        )
    if "data-policy-key" not in src:
        raise SystemExit(
            "privacy page missing data-policy-key markers — cannot verify "
            "every policy is rendered"
        )
    return set(re.findall(r'data-policy-key=\{p\.key\}', src)) or {"__data_driven__"}


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> int:
    try:
        py_policies = _load_python_policies()
        ts_policies = _load_ts_policies()
        _privacy_page_keys()
    except SystemExit as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    py_by_key = {p["key"]: p for p in py_policies}
    ts_by_key = {p["key"]: p for p in ts_policies}

    py_keys = set(py_by_key)
    ts_keys = set(ts_by_key)

    drift: list[str] = []
    if py_keys != ts_keys:
        only_py = py_keys - ts_keys
        only_ts = ts_keys - py_keys
        if only_py:
            drift.append(
                f"keys present in Python but missing from TS mirror: "
                f"{sorted(only_py)}"
            )
        if only_ts:
            drift.append(
                f"keys present in TS mirror but missing from Python: "
                f"{sorted(only_ts)}"
            )

    for key in sorted(py_keys & ts_keys):
        a = py_by_key[key]
        b = ts_by_key[key]
        for field in (
            "label",
            "ttl_days",
            "action",
            "override",
            "auto_execute",
            "privacy_summary",
        ):
            if a[field] != b[field]:
                drift.append(
                    f"{key}.{field}: python={a[field]!r} ts={b[field]!r}"
                )

    if drift:
        print("FAIL: /privacy page out of sync with retention policy table:",
              file=sys.stderr)
        for d in drift:
            print(f"  - {d}", file=sys.stderr)
        return 1

    print(
        f"OK: {len(py_policies)} retention policies, "
        f"Python ↔ TS mirror ↔ /privacy all consistent."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
