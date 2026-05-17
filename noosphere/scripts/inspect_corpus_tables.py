"""One-shot diagnostic: did reextract_corpus.py write to the table the
triage UI actually reads from?

The Theseus corpus is stored across two parallel tables — a lowercase
`conclusion` table (noosphere's SQLModel layer) and a capitalized
`Conclusion` table (theseus-codex's Prisma layer). The triage UI at
`/(authed)/extractor/re-extract` reads from the Prisma table only.
This script tells you which table is which size, which one a
specific row lives in, and whether `reextract_corpus.py`'s writes
landed where the UI can see them.

Usage (with DATABASE_URL exported in the shell):

    python noosphere/scripts/inspect_corpus_tables.py
    python noosphere/scripts/inspect_corpus_tables.py --id c_de2d6e313faf456889c16c8f
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Bootstrap PYTHONPATH so the script works whether or not the package
# is pip-installed in the active venv.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "noosphere"))

from noosphere.store import Store  # noqa: E402
from noosphere.forecasts.scheduler import database_url_from_env  # noqa: E402
from sqlalchemy import text, inspect  # noqa: E402


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--id",
        default="c_de2d6e313faf456889c16c8f",
        help="A specific conclusion id to look up in each table.",
    )
    args = p.parse_args(argv)

    store = Store.from_database_url(database_url_from_env())
    insp = inspect(store.engine)
    tables = set(insp.get_table_names())

    has_lower = "conclusion" in tables
    has_upper = "Conclusion" in tables
    print(f"Tables present: lowercase 'conclusion'? {has_lower} | "
          f"capitalized 'Conclusion'? {has_upper}")

    with store.engine.connect() as conn:
        if has_lower:
            n_sqlmodel = conn.execute(
                text("SELECT count(*) FROM conclusion")
            ).scalar()
            n_sqlmodel_with_rationale = conn.execute(
                text(
                    "SELECT count(*) FROM conclusion "
                    "WHERE payload_json LIKE '%\"rationale\":%' "
                    "AND payload_json NOT LIKE '%\"rationale\":\"\"%'"
                )
            ).scalar()
            print(
                f"\nLowercase `conclusion` (sqlmodel)"
                f"\n  total rows                       : {n_sqlmodel}"
                f"\n  rows w/ non-empty rationale-shape: {n_sqlmodel_with_rationale}"
            )

        if has_upper:
            n_prisma = conn.execute(text('SELECT count(*) FROM "Conclusion"')).scalar()
            n_prisma_rat = conn.execute(
                text(
                    'SELECT count(*) FROM "Conclusion" '
                    "WHERE rationale IS NOT NULL AND rationale != ''"
                )
            ).scalar()
            n_prisma_pkind = conn.execute(
                text(
                    'SELECT count(*) FROM "Conclusion" '
                    'WHERE "principleKind" IS NOT NULL'
                )
            ).scalar()
            print(
                f"\nCapitalized `Conclusion` (Prisma)"
                f"\n  total rows                       : {n_prisma}"
                f"\n  rows w/ non-empty rationale      : {n_prisma_rat}"
                f"\n  rows w/ principleKind set        : {n_prisma_pkind}"
            )

        print(f"\nTarget row lookup: {args.id}")

        if has_lower:
            r = conn.execute(
                text("SELECT payload_json FROM conclusion WHERE id = :id"),
                {"id": args.id},
            ).fetchone()
            if r:
                print("  in lowercase `conclusion`: PRESENT")
                print(f"    payload preview: {r[0][:400]}...")
            else:
                print("  in lowercase `conclusion`: ABSENT")

        if has_upper:
            r = conn.execute(
                text(
                    'SELECT text, rationale, "principleKind" '
                    'FROM "Conclusion" WHERE id = :id'
                ),
                {"id": args.id},
            ).fetchone()
            if r:
                print("  in capitalized `Conclusion`: PRESENT")
                print(f"    text         : {(r[0] or '')[:160]}")
                print(f"    rationale    : {(r[1] or '')[:300]}")
                print(f"    principleKind: {r[2]}")
            else:
                print("  in capitalized `Conclusion`: ABSENT")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
