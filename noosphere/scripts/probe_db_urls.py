"""Try each candidate DATABASE_URL across your local .env files and
report which one currently authenticates against Supabase.

The Supabase password rotates; the locally-cached copies drift out of
sync. This probe is a fast way to find which file has the live
password without needing the Vercel CLI or the Supabase dashboard.

Usage:
    python noosphere/scripts/probe_db_urls.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "noosphere"))

from sqlalchemy import create_engine, text  # noqa: E402


CANDIDATE_FILES = [
    _REPO_ROOT / ".vercel" / ".env.production.local",
    _REPO_ROOT / "theseus-codex" / ".env",
    _REPO_ROOT / "current_events_api" / ".env",
    _REPO_ROOT / ".env",
]


def _read_db_url(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        m = re.match(r'^\s*DATABASE_URL\s*=\s*["\']?([^"\'\n]+)["\']?\s*$', line)
        if m:
            return m.group(1).strip()
    return None


def _redact(url: str) -> str:
    return re.sub(r"://([^:]+):[^@]+@", r"://\1:***@", url)


def _clean_for_psycopg2(url: str) -> str:
    # psycopg2 doesn't accept ?pgbouncer=true as a DSN option; strip it.
    cleaned = re.sub(r"[?&]pgbouncer=true", "", url)
    cleaned = re.sub(r"\?$", "", cleaned)
    return cleaned


def main() -> int:
    seen: dict[str, list[str]] = {}
    for path in CANDIDATE_FILES:
        url = _read_db_url(path)
        if url is None:
            print(f"[skip]  {path.relative_to(_REPO_ROOT)}: no DATABASE_URL")
            continue
        seen.setdefault(url, []).append(str(path.relative_to(_REPO_ROOT)))

    if not seen:
        print("\nNo DATABASE_URL found in any candidate file. "
              "Get the current password from Supabase dashboard:")
        print("  https://supabase.com/dashboard → your project → "
              "Settings → Database → Connection string")
        return 2

    print(f"\nFound {len(seen)} distinct DATABASE_URL value(s) across files.\n")

    winner: str | None = None
    for url, files in seen.items():
        print(f"--- candidate: {_redact(url)}")
        print(f"    from files: {', '.join(files)}")
        try:
            eng = create_engine(_clean_for_psycopg2(url))
            with eng.connect() as conn:
                n = conn.execute(text('SELECT count(*) FROM "Conclusion"')).scalar()
            print(f"    AUTH OK — {n} Conclusion rows visible")
            if winner is None:
                winner = url
        except Exception as exc:
            msg = str(exc)
            # Trim long stack traces; keep just the first auth-relevant line.
            first_line = msg.splitlines()[0] if msg else repr(exc)
            print(f"    AUTH FAILED: {first_line[:200]}")
        print()

    print("=" * 70)
    if winner:
        print(f"\nA WORKING DATABASE_URL was found in:")
        for f in seen[winner]:
            print(f"  {f}")
        print(f"\nIn your shell, run:")
        print(f"  set -a")
        print(f"  source {seen[winner][0]}")
        print(f"  set +a")
    else:
        print("\nNo file has a working password. The live password isn't")
        print("cached locally. Get it from Supabase dashboard:")
        print("  https://supabase.com/dashboard → your project → ")
        print("  Settings → Database → Connection string (pooler, port 6543)")
        print("\nThen export it directly in your shell:")
        print('  export DATABASE_URL=\'postgresql://postgres.<ref>:'
              '<PASSWORD>@aws-1-us-west-2.pooler.supabase.com:6543'
              '/postgres?pgbouncer=true\'')
    return 0 if winner else 1


if __name__ == "__main__":
    raise SystemExit(main())
