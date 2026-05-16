#!/usr/bin/env python3
"""Generate the slide-11 ("What's working") snapshot for the pitch deck.

Reads counts from the live Codex database and writes
``slide11_data.tex`` next to this script, plus ``team_data.tex`` for
the team slide. The deck build script depends on the existence and
non-emptiness of both files.

By contract: this script must not invent numbers. If the database is
unreachable, missing, or returns nothing for a query, the script
exits non-zero so the build aborts loudly rather than ship a stale
or fabricated snapshot.

Database URL resolution (first hit wins):
  1. ``DATABASE_URL`` env var
  2. ``THESEUS_DATABASE_URL`` env var

Usage:
    python live_snapshot.py [--out-dir <dir>]
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
    from sqlalchemy.exc import SQLAlchemyError
except ImportError:  # pragma: no cover - surfaces the missing dep early.
    sys.stderr.write(
        "live_snapshot.py: SQLAlchemy is required. "
        "Install with `pip install sqlalchemy psycopg[binary]`.\n"
    )
    raise


HERE = Path(__file__).resolve().parent


class SnapshotError(RuntimeError):
    """Raised when the snapshot cannot be produced from the live DB."""


@dataclass(frozen=True)
class Snapshot:
    algorithms_active: int
    principles_total: int
    memos_published: int
    invocations_total: int
    invocations_resolved: int
    invocations_correct: int

    @property
    def hit_rate(self) -> float | None:
        if self.invocations_resolved == 0:
            return None
        return self.invocations_correct / self.invocations_resolved


@dataclass(frozen=True)
class TeamMember:
    display_name: str
    role_title: str
    bio: str


def database_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("THESEUS_DATABASE_URL")
    if not url:
        raise SnapshotError(
            "Neither DATABASE_URL nor THESEUS_DATABASE_URL is set. "
            "The deck refuses to ship without live numbers."
        )
    return url


def open_engine(url: str) -> Engine:
    try:
        return create_engine(url, future=True)
    except SQLAlchemyError as exc:  # pragma: no cover - thin wrapper
        raise SnapshotError(f"could not open DB connection: {exc}") from exc


def _scalar(engine: Engine, sql: str) -> int:
    try:
        with engine.connect() as conn:
            row = conn.execute(text(sql)).scalar()
    except SQLAlchemyError as exc:
        raise SnapshotError(f"query failed: {sql!r}: {exc}") from exc
    if row is None:
        raise SnapshotError(f"query returned NULL: {sql!r}")
    return int(row)


def gather_snapshot(engine: Engine) -> Snapshot:
    algorithms_active = _scalar(
        engine,
        'SELECT COUNT(*) FROM "LogicalAlgorithm" WHERE status = \'ACTIVE\'',
    )
    principles_total = _scalar(engine, 'SELECT COUNT(*) FROM "Principle"')
    memos_published = _scalar(
        engine,
        'SELECT COUNT(*) FROM "InvestmentMemo" WHERE status = \'PUBLIC\'',
    )
    invocations_total = _scalar(
        engine, 'SELECT COUNT(*) FROM "AlgorithmInvocation"'
    )
    invocations_resolved = _scalar(
        engine,
        'SELECT COUNT(*) FROM "AlgorithmInvocation" WHERE "resolvedAt" IS NOT NULL',
    )
    invocations_correct = _scalar(
        engine,
        'SELECT COUNT(*) FROM "AlgorithmInvocation" WHERE correctness = \'CORRECT\'',
    )
    return Snapshot(
        algorithms_active=algorithms_active,
        principles_total=principles_total,
        memos_published=memos_published,
        invocations_total=invocations_total,
        invocations_resolved=invocations_resolved,
        invocations_correct=invocations_correct,
    )


def gather_team(engine: Engine) -> list[TeamMember]:
    sql = (
        'SELECT COALESCE(NULLIF("displayName", \'\'), name) AS display_name, '
        '       COALESCE("roleTitle", \'\') AS role_title, '
        '       COALESCE(bio, \'\') AS bio '
        'FROM "Founder" '
        'WHERE role IN (\'admin\', \'founder\') AND bio IS NOT NULL '
        'ORDER BY "createdAt" ASC, name ASC'
    )
    try:
        with engine.connect() as conn:
            rows = list(conn.execute(text(sql)))
    except SQLAlchemyError as exc:
        raise SnapshotError(f"team query failed: {exc}") from exc
    return [
        TeamMember(
            display_name=str(row.display_name or "").strip() or "(name withheld)",
            role_title=str(row.role_title or "").strip(),
            bio=str(row.bio or "").strip(),
        )
        for row in rows
        if str(row.bio or "").strip()
    ]


_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(value: str) -> str:
    out = []
    for ch in value:
        out.append(_LATEX_ESCAPES.get(ch, ch))
    return "".join(out)


def render_snapshot(snapshot: Snapshot) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    hit_rate_str = (
        f"{snapshot.hit_rate * 100:.0f}\\%" if snapshot.hit_rate is not None else "n/a"
    )
    lines: list[str] = [
        "% Auto-generated by live_snapshot.py. Do not edit by hand.",
        f"% Generated at {generated}",
        "",
        r"\begin{tabular}{@{}>{\raggedright\arraybackslash}p{0.45\textwidth}@{\hspace{0.05\textwidth}}>{\raggedright\arraybackslash}p{0.4\textwidth}@{}}",
        rf"\sffamily\bfseries\color{{amber}}Algorithms active & {snapshot.algorithms_active} \\[0.18in]",
        rf"\sffamily\bfseries\color{{amber}}Principles in corpus & {snapshot.principles_total} \\[0.18in]",
        rf"\sffamily\bfseries\color{{amber}}Memos published & {snapshot.memos_published} \\[0.18in]",
        rf"\sffamily\bfseries\color{{amber}}Invocations recorded & {snapshot.invocations_total} \\[0.18in]",
        rf"\sffamily\bfseries\color{{amber}}Invocations resolved & {snapshot.invocations_resolved} \\[0.18in]",
        rf"\sffamily\bfseries\color{{amber}}Calibration (correct / resolved) & {snapshot.invocations_correct} / {snapshot.invocations_resolved} ({hit_rate_str}) \\",
        r"\end{tabular}",
    ]
    return "\n".join(lines) + "\n"


def render_team(members: Iterable[TeamMember]) -> str:
    items = list(members)
    if not items:
        return (
            "% Auto-generated by live_snapshot.py. Do not edit by hand.\n"
            r"\slidesub{No public team members are configured in the founder table.}"
            "\n"
        )
    lines: list[str] = [
        "% Auto-generated by live_snapshot.py. Do not edit by hand.",
        r"\begin{itemize}[leftmargin=0.35in,itemsep=0.18in,topsep=0]",
    ]
    for member in items:
        role = (
            rf" \textit{{\color{{amberdim}}{latex_escape(member.role_title)}}}"
            if member.role_title
            else ""
        )
        bio = latex_escape(member.bio)
        lines.append(
            rf"  \item \textbf{{{latex_escape(member.display_name)}}}{role}\\ {bio}"
        )
    lines.append(r"\end{itemize}")
    return "\n".join(lines) + "\n"


def write_file(path: Path, content: str) -> None:
    if not content.strip():
        raise SnapshotError(f"refusing to write empty file at {path}")
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=HERE,
        help="directory to write slide11_data.tex and team_data.tex into",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    try:
        url = database_url()
        engine = open_engine(url)
        snapshot = gather_snapshot(engine)
        team = gather_team(engine)
    except SnapshotError as exc:
        sys.stderr.write(f"live_snapshot.py: {exc}\n")
        return 2

    snapshot_tex = render_snapshot(snapshot)
    team_tex = render_team(team)

    try:
        write_file(args.out_dir / "slide11_data.tex", snapshot_tex)
        write_file(args.out_dir / "team_data.tex", team_tex)
    except SnapshotError as exc:
        sys.stderr.write(f"live_snapshot.py: {exc}\n")
        return 2

    sys.stdout.write(
        "live_snapshot.py: wrote slide11_data.tex and team_data.tex "
        f"(algorithms={snapshot.algorithms_active}, principles={snapshot.principles_total}, "
        f"memos={snapshot.memos_published}, invocations={snapshot.invocations_total})\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
