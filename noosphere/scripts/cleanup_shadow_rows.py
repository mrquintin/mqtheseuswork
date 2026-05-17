"""One-shot helper: delete shadow rows in the lowercase SQLModel
`conclusion` table that were written by an earlier broken version of
`reextract_corpus.py`. Those rows live in noosphere's own table but
the triage UI reads from the capitalized Prisma `Conclusion` table —
the shadow rows are orphans that just confuse the dedup logic in
`Store.list_conclusions()`.

Usage (with DATABASE_URL exported):

    # Dry-run: show what would be deleted without deleting:
    python noosphere/scripts/cleanup_shadow_rows.py --dry-run

    # Actually delete:
    python noosphere/scripts/cleanup_shadow_rows.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "noosphere"))

from noosphere.store import Store  # noqa: E402
from noosphere.forecasts.scheduler import database_url_from_env  # noqa: E402
from sqlalchemy import text, inspect  # noqa: E402


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be deleted; delete nothing.")
    args = p.parse_args(argv)

    store = Store.from_database_url(database_url_from_env())
    insp = inspect(store.engine)
    tables = set(insp.get_table_names())

    if "conclusion" not in tables:
        print("Lowercase `conclusion` table does not exist. Nothing to clean up.")
        return 0

    with store.engine.connect() as conn:
        rows = conn.execute(text("SELECT id FROM conclusion")).fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            print("Lowercase `conclusion` table is already empty.")
            return 0

        print(f"Found {len(ids)} shadow rows in lowercase `conclusion`:")
        for rid in ids[:20]:
            print(f"  - {rid}")
        if len(ids) > 20:
            print(f"  ... and {len(ids) - 20} more")

        if args.dry_run:
            print("\n(dry-run) Not deleting. Re-run without --dry-run to commit.")
            return 0

        deleted = conn.execute(text("DELETE FROM conclusion")).rowcount
        conn.commit()
        print(f"\nDeleted {deleted} shadow row(s) from lowercase `conclusion`.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
