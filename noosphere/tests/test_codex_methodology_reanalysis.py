from __future__ import annotations

from noosphere.codex_bridge import ingest_from_codex
from noosphere.codex_methodology_reanalysis import reanalyze_methodology_profiles


METHODOLOGY_TEXT = """
The purpose of the school is not credentialing alone. We should reduce the
institution to first principles, constraints, and the mechanism by which a
student actually discovers truth. The same frame can transfer to other
institutions because the method is about how a system reasons, not only what
education happens to conclude. The strongest objection is that a superficial
analogy could fail, so evidence and confidence have to discipline the transfer.
"""


def test_ingest_writes_methodology_profiles_and_upload_method_count(
    fake_codex_db, codex_sqlite_url, upload_factory,
) -> None:
    uid = upload_factory(
        mime="text/plain",
        text=METHODOLOGY_TEXT,
        original_name="method.txt",
        title="Method transcript",
    )

    result = ingest_from_codex(
        upload_id=uid,
        use_llm=False,
        dry_run=False,
        codex_db_url=codex_sqlite_url,
    )

    rows = fake_codex_db.execute(
        '''SELECT "patternType", title
           FROM "MethodologyProfile"
           WHERE "uploadId" = ?''',
        (uid,),
    ).fetchall()
    upload = fake_codex_db.execute(
        'SELECT "methodCount" FROM "Upload" WHERE id = ?',
        (uid,),
    ).fetchone()

    assert result.num_methodology_profiles_written >= 2
    assert len(rows) >= 2
    assert upload["methodCount"] == result.num_methodology_profiles_written
    assert {row["patternType"] for row in rows} >= {
        "first_principles_decomposition",
        "analogical_transfer",
    }

    fake_codex_db.execute(
        '''UPDATE "MethodologyProfile"
           SET title = ?
           WHERE "uploadId" = ? AND "patternType" = ?''',
        ("stale title", uid, "analogical_transfer"),
    )
    fake_codex_db.commit()

    again = ingest_from_codex(
        upload_id=uid,
        use_llm=False,
        dry_run=False,
        codex_db_url=codex_sqlite_url,
    )
    again_rows = fake_codex_db.execute(
        '''SELECT "patternType", title
           FROM "MethodologyProfile"
           WHERE "uploadId" = ?''',
        (uid,),
    ).fetchall()
    refreshed = {row["patternType"]: row["title"] for row in again_rows}

    assert len(again_rows) == len(rows)
    assert (
        again.num_methodology_profiles_written
        == result.num_methodology_profiles_written
    )
    assert refreshed["analogical_transfer"] == "Analogical transfer"


def test_reanalysis_is_dry_run_by_default_and_apply_is_idempotent(
    fake_codex_db, codex_sqlite_url, upload_factory,
) -> None:
    uid = upload_factory(
        mime="text/plain",
        text=METHODOLOGY_TEXT,
        original_name="method.txt",
        title="Method transcript",
    )

    dry = reanalyze_methodology_profiles(codex_db_url=codex_sqlite_url)
    assert dry.dry_run is True
    assert dry.uploads_scanned == 1
    assert dry.profiles_found >= 2
    assert (
        fake_codex_db.execute(
            'SELECT COUNT(*) AS n FROM "MethodologyProfile"'
        ).fetchone()["n"]
        == 0
    )

    applied = reanalyze_methodology_profiles(
        codex_db_url=codex_sqlite_url,
        dry_run=False,
    )
    again = reanalyze_methodology_profiles(
        codex_db_url=codex_sqlite_url,
        dry_run=False,
    )
    count = fake_codex_db.execute(
        'SELECT COUNT(*) AS n FROM "MethodologyProfile" WHERE "uploadId" = ?',
        (uid,),
    ).fetchone()["n"]

    assert applied.profiles_written >= 2
    assert again.profiles_written >= 2
    assert count == applied.profiles_written
