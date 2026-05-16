"""Frontend route smoke.

What it catches
---------------
* A new SSR route 500s because it imports a deleted module.
* A route renders an empty / error body (NextErrorBoundary or
  "An error occurred").
* A page file exists but is empty / lost its default export.

How it runs
-----------
The check has two modes, layered so the harness always returns *some*
signal:

1. **Static** (always run) — walk ``theseus-codex/src/app/`` for every
   ``page.tsx``, verify the file has a default export and that every
   relative ``import`` resolves to a file that exists on disk. This
   catches the most common regression ("deleted a module, forgot to
   update an import") without needing Node.js running.

2. **Live** (run when ``PUBLIC_BASE_URL`` is set) — GET every route
   against the dev/preview server, assert ``status in {200, 302,
   304, 410}``, assert the body does not contain a Next error
   boundary, assert at least one ``<main>`` element. Authed routes
   carry founder cookies.

The harness deliberately *does not* boot ``next dev`` itself: the
boot cost (~25s on M-series, longer on first run) would blow the
4-minute budget. CI starts the server in a separate workflow step
and passes ``PUBLIC_BASE_URL``.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import _fixtures


ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = ROOT / "theseus-codex" / "src" / "app"

# Status codes a smoke check tolerates. 410 covers the Round 18
# deletion-pass routes that intentionally return Gone.
ALLOWED_STATUS = {200, 302, 304, 308, 410}

ERROR_MARKERS = (
    "An error occurred",
    "NextErrorBoundary",
    "Application error: a server-side exception",
)

# Routes that intentionally return a non-200 even with cookies (login
# walls, redirects to external auth, etc.). Adding to this list
# requires a comment justifying the exclusion.
KNOWN_NON_200: dict[str, set[int]] = {
    # /api routes that some pages embed — pages should still resolve.
}


@dataclass
class RouteResult:
    route: str
    authed: bool
    status: int | None
    ok: bool
    detail: str
    body_snippet: str = ""


def _route_for_file(page: Path) -> tuple[str, bool]:
    """Map a ``page.tsx`` path to a URL path + authed flag."""
    rel = page.relative_to(APP_DIR).parent
    parts: list[str] = []
    authed = False
    for part in rel.parts:
        if part == "(authed)":
            authed = True
            continue
        if part.startswith("(") and part.endswith(")"):
            # Other route groups are URL-invisible.
            continue
        if part.startswith("[") and part.endswith("]"):
            parts.append(_fixtures.dynamic_segment_value(part))
            continue
        parts.append(part)
    url = "/" + "/".join(parts) if parts else "/"
    return url, authed


_RELATIVE_IMPORT = re.compile(
    r"""(?:^|\s)(?:import|export)\s+(?:[^'"]*?\s+from\s+)?['"](?P<spec>\.{1,2}/[^'"]+)['"]""",
    re.MULTILINE,
)
_AT_ALIAS_IMPORT = re.compile(
    r"""(?:^|\s)(?:import|export)\s+(?:[^'"]*?\s+from\s+)?['"]@/(?P<spec>[^'"]+)['"]""",
    re.MULTILINE,
)
_DEFAULT_EXPORT = re.compile(r"^export\s+default\s+", re.MULTILINE)


def _resolve_import(source: Path, spec: str, *, alias_root: Path) -> Path | None:
    """Resolve an import spec to a concrete file on disk, or None."""
    if spec.startswith("."):
        base = (source.parent / spec).resolve()
    else:
        base = (alias_root / spec).resolve()
    if base.is_file():
        return base
    for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".json"):
        candidate = base.with_suffix(base.suffix + ext) if base.suffix else base.with_suffix(ext)
        if candidate.is_file():
            return candidate
        # Try literal extension append for paths without an existing
        # suffix (e.g. "../foo" → "../foo.ts").
        candidate2 = Path(str(base) + ext)
        if candidate2.is_file():
            return candidate2
    # Index file in directory.
    if base.is_dir():
        for ext in ("index.ts", "index.tsx", "index.js", "index.jsx"):
            if (base / ext).is_file():
                return base / ext
    return None


def _static_check(page: Path) -> tuple[bool, str]:
    """Verify the page file has a default export and resolvable imports."""
    try:
        text = page.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"unreadable: {exc}"
    if not text.strip():
        return False, "empty file"
    if not _DEFAULT_EXPORT.search(text):
        return False, "no default export"
    alias_root = ROOT / "theseus-codex" / "src"
    bad: list[str] = []
    for match in _RELATIVE_IMPORT.finditer(text):
        spec = match.group("spec")
        if _resolve_import(page, spec, alias_root=alias_root) is None:
            bad.append(spec)
    for match in _AT_ALIAS_IMPORT.finditer(text):
        spec = match.group("spec")
        if _resolve_import(page, spec, alias_root=alias_root) is None:
            # Many `@/lib/...` paths are routed by tsconfig — only flag
            # ones that have no file at the alias_root tree at all.
            if not (alias_root / spec).exists() and not any(
                (alias_root / spec).with_suffix(ext).exists()
                for ext in (".ts", ".tsx", ".js", ".jsx")
            ):
                bad.append(f"@/{spec}")
    if bad:
        return False, f"unresolved imports: {bad[:5]}"
    return True, "static-ok"


def _live_check(
    base_url: str, route: str, authed: bool, timeout: float
) -> RouteResult:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(base_url.rstrip("/") + route)
    if authed:
        cookies = "; ".join(f"{k}={v}" for k, v in _fixtures.founder_session_cookies().items())
        req.add_header("Cookie", cookies)
        req.add_header("X-Theseus-Smoke", "1")
    req.add_header("User-Agent", "theseus-smoke/1.0")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixture URL only
            status = resp.status
            body = resp.read(64 * 1024).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
    except (urllib.error.URLError, TimeoutError) as exc:
        return RouteResult(route, authed, None, False, f"unreachable: {exc}")
    elapsed = time.monotonic() - started
    snippet = body[:1000]
    allowed = ALLOWED_STATUS | KNOWN_NON_200.get(route, set())
    if status not in allowed:
        return RouteResult(route, authed, status, False, f"unexpected status {status}", snippet)
    for marker in ERROR_MARKERS:
        if marker in body:
            return RouteResult(
                route, authed, status, False, f"body contains error marker {marker!r}", snippet
            )
    if status == 200 and "<main" not in body and "<!doctype" in body.lower():
        return RouteResult(
            route, authed, status, False, "200 HTML response missing <main>", snippet
        )
    detail = f"ok ({elapsed*1000:.0f}ms)"
    return RouteResult(route, authed, status, True, detail)


def collect_routes() -> list[tuple[str, bool, Path]]:
    """Walk ``app/`` and return ``[(route, authed, page_path), ...]``."""
    if not APP_DIR.is_dir():
        return []
    out: list[tuple[str, bool, Path]] = []
    for page in sorted(APP_DIR.rglob("page.tsx")):
        route, authed = _route_for_file(page)
        out.append((route, authed, page))
    return out


def run(output_dir: Path, *, base_url: str | None = None, timeout: float = 10.0) -> dict[str, Any]:
    started = time.monotonic()
    checks: list[dict[str, Any]] = []
    routes = collect_routes()
    static_failures = 0
    for route, authed, page in routes:
        ok, detail = _static_check(page)
        if not ok:
            static_failures += 1
        checks.append(
            {
                "name": f"static::{route}",
                "ok": ok,
                "detail": detail,
                "route": route,
                "authed": authed,
                "page": str(page.relative_to(ROOT)),
            }
        )
    live_failures = 0
    live_attempted = False
    if base_url:
        live_attempted = True
        for route, authed, _page in routes:
            res = _live_check(base_url, route, authed, timeout=timeout)
            if not res.ok:
                live_failures += 1
            checks.append(
                {
                    "name": f"live::{route}",
                    "ok": res.ok,
                    "detail": res.detail,
                    "route": route,
                    "authed": authed,
                    "status": res.status,
                    "body_snippet": res.body_snippet if not res.ok else "",
                }
            )
    duration = time.monotonic() - started
    payload = {
        "section": "frontend-routes",
        "ok": static_failures == 0 and live_failures == 0,
        "duration_s": round(duration, 3),
        "checks": checks,
        "summary": {
            "routes_total": len(routes),
            "static_failures": static_failures,
            "live_attempted": live_attempted,
            "live_failures": live_failures,
            "base_url": base_url,
        },
        "perf_warning": f"section exceeded 30s budget ({duration:.1f}s)" if duration > 30 else None,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "frontend-routes.json").write_text(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default=os.environ.get("PUBLIC_BASE_URL"))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    result = run(args.output_dir, base_url=args.base_url, timeout=args.timeout)
    raise SystemExit(0 if result["ok"] else 1)
